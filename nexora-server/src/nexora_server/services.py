"""Business logic shared by the REST API and the streaming endpoints (synchronous DB code)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from nexora_audio import NexoraConfig, TurnConfig
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from nexora_server.db import ApiKey, AuditEvent, Organization, Profile, SessionRecord, utcnow
from nexora_server.security import Principal, generate_api_key, key_prefix, verify_key

# Settings decided per stream (by the connection), not by a stored profile
_STREAM_OWNED = {"sample_rate", "channels", "vad", "output_queue_chunks"}


class ServiceError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


# ---- auth -------------------------------------------------------------------------


def authenticate_key(db: Session, plaintext: str, pepper: str) -> Principal | None:
    prefix = key_prefix(plaintext)
    if prefix is None:
        return None
    key = db.scalar(select(ApiKey).where(ApiKey.prefix == prefix))
    if key is None or key.revoked_at is not None or not verify_key(plaintext, key.key_hash, pepper):
        return None
    org = db.get(Organization, key.org_id)
    if org is None or not org.active:
        return None
    now = utcnow()
    last = key.last_used_at
    if last is None or now - _aware(last) > timedelta(minutes=1):  # throttle writes
        key.last_used_at = now
    return Principal(key.org_id, frozenset(key.scopes), f"key:{key.id}", api_key_id=key.id)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def audit(db: Session, who: Principal, action: str, org_id: str | None, **details: Any) -> None:
    db.add(AuditEvent(org_id=org_id, actor=who.actor, action=action, details=details))


# ---- organizations and keys ----------------------------------------------------------


def create_org(db: Session, who: Principal, pepper: str, **fields: Any) -> tuple[Organization, str]:
    org = Organization(**fields)
    db.add(org)
    db.flush()
    _, plaintext = create_key(db, who, pepper, org.id, "initial admin key", list(_ALL_SCOPES))
    audit(db, who, "org.create", org.id, name=org.name)
    return org, plaintext


_ALL_SCOPES = ("stream", "admin", "usage:read")


def create_key(
    db: Session, who: Principal, pepper: str, org_id: str, name: str, scopes: list[str]
) -> tuple[ApiKey, str]:
    bad = set(scopes) - set(_ALL_SCOPES)
    if bad:
        raise ServiceError(422, f"unknown scopes: {sorted(bad)}")
    new = generate_api_key(pepper)
    key = ApiKey(org_id=org_id, name=name, prefix=new.prefix, key_hash=new.key_hash, scopes=scopes)
    db.add(key)
    db.flush()
    audit(db, who, "key.create", org_id, key_id=key.id, scopes=scopes)
    return key, new.plaintext


def get_org(db: Session, org_id: str) -> Organization:
    org = db.get(Organization, org_id)
    if org is None:
        raise ServiceError(404, "organization not found")
    return org


# ---- profiles -----------------------------------------------------------------------


def validate_profile(audio: dict[str, Any], turns: dict[str, Any] | None) -> None:
    owned = _STREAM_OWNED & set(audio)
    if owned:
        raise ServiceError(422, f"set per stream, not in profiles: {sorted(owned)}")
    try:
        NexoraConfig(**audio)
        if turns is not None:
            TurnConfig(**turns)
    except (ValidationError, TypeError) as exc:
        raise ServiceError(422, f"invalid profile settings: {exc}") from exc


def resolve_profile(db: Session, org_id: str, ref: str | None) -> Profile | None:
    """By id or name; ``None`` means the org's default profile (if any)."""
    q = select(Profile).where(Profile.org_id == org_id)
    if ref is None:
        return db.scalar(q.where(Profile.is_default.is_(True)))
    prof = db.scalar(q.where((Profile.id == ref) | (Profile.name == ref)))
    if prof is None:
        raise ServiceError(404, f"profile {ref!r} not found")
    return prof


def set_default_profile(db: Session, org_id: str, profile: Profile) -> None:
    for other in db.scalars(select(Profile).where(Profile.org_id == org_id)):
        other.is_default = other.id == profile.id


# ---- usage --------------------------------------------------------------------------


def month_start(now: datetime | None = None) -> datetime:
    now = now or utcnow()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def used_seconds(db: Session, org_id: str, since: datetime) -> float:
    """Audio of calls that ended since ``since``: counted when a call ends, as billing does
    (E9), so the usage pages, the quota and the invoice agree."""
    total = db.scalar(
        select(func.coalesce(func.sum(SessionRecord.audio_seconds), 0.0)).where(
            SessionRecord.org_id == org_id, SessionRecord.ended_at >= since
        )
    )
    return float(total or 0.0)


def quota_remaining_s(db: Session, org: Organization) -> float | None:
    if org.monthly_minutes_quota is None:
        return None
    return org.monthly_minutes_quota * 60.0 - used_seconds(db, org.id, month_start())


def usage_by_day(db: Session, org_id: str, start: datetime, end: datetime) -> list[dict[str, Any]]:
    """Audio minutes and calls per UTC day, by the day each call ended."""
    rows = db.execute(
        select(SessionRecord.ended_at, SessionRecord.audio_seconds).where(
            SessionRecord.org_id == org_id,
            SessionRecord.ended_at >= start,
            SessionRecord.ended_at < end,
        )
    ).all()
    days: dict[str, list[float]] = {}
    for ended, secs in rows:
        if ended is None:  # excluded by the query; for the type checker
            continue
        d = _aware(ended).date().isoformat()
        days.setdefault(d, [0.0, 0.0])
        days[d][0] += secs
        days[d][1] += 1
    return [
        {"date": d, "audio_minutes": round(v[0] / 60.0, 3), "sessions": int(v[1])}
        for d, v in sorted(days.items())
    ]


def active_sessions(db: Session, org_id: str) -> int:
    """Calls running now for the organization, on every server (lost ones are swept)."""
    return int(
        db.scalar(
            select(func.count())
            .select_from(SessionRecord)
            .where(SessionRecord.org_id == org_id, SessionRecord.status == "active")
        )
        or 0
    )


LOST_REASON = "lost: no heartbeat from the server running the call"


def sweep_stale_sessions(db: Session, stale_after_s: float, now: datetime | None = None) -> int:
    """Close calls whose server stopped without ending them (killed, crashed, node lost).

    They end at their last heartbeat with the audio seconds saved then, so billing counts
    them (late, in the next report). Several servers may sweep at once: the update only
    touches sessions that are still active and stale.
    """
    cutoff = (now or utcnow()) - timedelta(seconds=stale_after_s)
    last_seen = func.coalesce(SessionRecord.heartbeat_at, SessionRecord.started_at)
    stale = list(
        db.scalars(
            select(SessionRecord)
            .where(SessionRecord.status == "active", last_seen < cutoff)
            .with_for_update(skip_locked=True)
            .limit(500)
        )
    )
    for rec in stale:
        rec.status = "failed"
        rec.close_code = 1011
        rec.close_reason = LOST_REASON
        rec.ended_at = rec.heartbeat_at or rec.started_at
    return len(stale)
