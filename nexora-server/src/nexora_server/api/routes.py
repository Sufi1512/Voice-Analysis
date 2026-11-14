"""REST API: organizations, API keys, profiles, session tokens, sessions, usage, audit."""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from nexora_server.api import schemas as s
from nexora_server.db import (
    ApiKey,
    AuditEvent,
    Organization,
    Profile,
    SessionRecord,
    SsoMember,
    UsageReport,
    utcnow,
)
from nexora_server.deps import (
    get_db,
    get_principal,
    get_settings,
    org_for,
    require,
    require_superadmin,
)
from nexora_server.relay_policy import RelayTargetError, check_relay_target
from nexora_server.security import Principal, mint_session_token
from nexora_server.services import (
    ServiceError,
    audit,
    create_key,
    create_org,
    get_org,
    month_start,
    resolve_profile,
    set_default_profile,
    usage_by_day,
    used_seconds,
    validate_profile,
)
from nexora_server.settings import Settings

router = APIRouter(prefix="/v1")


def _svc(exc: ServiceError) -> HTTPException:
    return HTTPException(exc.status, exc.message)


# ---- who am I --------------------------------------------------------------------------


@router.get("/me", response_model=s.MeOut, tags=["auth"])
def who_am_i(who: Principal = Depends(get_principal), db: Session = Depends(get_db)) -> s.MeOut:
    org = db.get(Organization, who.org_id) if who.org_id else None
    return s.MeOut(
        actor=who.actor,
        superadmin=who.is_superadmin,
        org_id=who.org_id,
        org_name=org.name if org else None,
        scopes=sorted(who.scopes),
    )


# ---- organizations (super-admin) --------------------------------------------------------


@router.post("/orgs", response_model=s.OrgCreated, status_code=201, tags=["organizations"])
def create_organization(
    body: s.OrgCreate,
    who: Principal = Depends(require_superadmin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> s.OrgCreated:
    org, key = create_org(db, who, settings.secret_key, **body.model_dump())
    return s.OrgCreated(organization=s.OrgOut.model_validate(org), api_key=key)


@router.get("/orgs", response_model=list[s.OrgOut], tags=["organizations"])
def list_organizations(
    who: Principal = Depends(require_superadmin), db: Session = Depends(get_db)
) -> list[Organization]:
    return list(db.scalars(select(Organization).order_by(Organization.created_at)))


@router.get("/orgs/{org_id}", response_model=s.OrgOut, tags=["organizations"])
def get_organization(
    org_id: str, who: Principal = Depends(require("admin")), db: Session = Depends(get_db)
) -> Organization:
    try:
        return get_org(db, org_for(who, org_id))
    except ServiceError as exc:
        raise _svc(exc) from exc


@router.patch("/orgs/{org_id}", response_model=s.OrgOut, tags=["organizations"])
def update_organization(
    org_id: str,
    body: s.OrgUpdate,
    who: Principal = Depends(require_superadmin),
    db: Session = Depends(get_db),
) -> Organization:
    try:
        org = get_org(db, org_id)
    except ServiceError as exc:
        raise _svc(exc) from exc
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(org, k, v)
    audit(db, who, "org.update", org.id, **changes)
    return org


# ---- API keys ------------------------------------------------------------------------------


@router.post("/keys", response_model=s.KeyCreated, status_code=201, tags=["api keys"])
def create_api_key(
    body: s.KeyCreate,
    who: Principal = Depends(require("admin")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> s.KeyCreated:
    org_id = org_for(who, body.org_id)
    try:
        get_org(db, org_id)
        scopes = [str(x) for x in body.scopes]
        key, plaintext = create_key(db, who, settings.secret_key, org_id, body.name, scopes)
    except ServiceError as exc:
        raise _svc(exc) from exc
    return s.KeyCreated(key=s.KeyOut.model_validate(key), api_key=plaintext)


@router.get("/keys", response_model=list[s.KeyOut], tags=["api keys"])
def list_api_keys(
    org_id: str | None = None,
    who: Principal = Depends(require("admin")),
    db: Session = Depends(get_db),
) -> list[ApiKey]:
    oid = org_for(who, org_id)
    return list(db.scalars(select(ApiKey).where(ApiKey.org_id == oid).order_by(ApiKey.created_at)))


@router.delete("/keys/{key_id}", response_model=s.KeyOut, tags=["api keys"])
def revoke_api_key(
    key_id: str, who: Principal = Depends(require("admin")), db: Session = Depends(get_db)
) -> ApiKey:
    key = db.get(ApiKey, key_id)
    if key is None or (not who.is_superadmin and key.org_id != who.org_id):
        raise HTTPException(404, "key not found")
    if key.revoked_at is None:
        key.revoked_at = utcnow()
        audit(db, who, "key.revoke", key.org_id, key_id=key.id)
    return key


# ---- profiles -----------------------------------------------------------------------------


@router.post("/profiles", response_model=s.ProfileOut, status_code=201, tags=["profiles"])
def create_profile(
    body: s.ProfileIn, who: Principal = Depends(require("admin")), db: Session = Depends(get_db)
) -> Profile:
    org_id = org_for(who, body.org_id)
    try:
        validate_profile(body.audio_settings, body.turn_settings)
    except ServiceError as exc:
        raise _svc(exc) from exc
    exists = db.scalar(select(Profile).where(Profile.org_id == org_id, Profile.name == body.name))
    if exists:
        raise HTTPException(409, f"profile {body.name!r} already exists")
    prof = Profile(
        org_id=org_id,
        name=body.name,
        audio_settings=body.audio_settings,
        turn_settings=body.turn_settings,
    )
    db.add(prof)
    db.flush()
    if body.is_default:
        set_default_profile(db, org_id, prof)
    audit(db, who, "profile.create", org_id, profile_id=prof.id, name=prof.name)
    return prof


@router.get("/profiles", response_model=list[s.ProfileOut], tags=["profiles"])
def list_profiles(
    org_id: str | None = None,
    who: Principal = Depends(require("admin")),
    db: Session = Depends(get_db),
) -> list[Profile]:
    oid = org_for(who, org_id)
    return list(db.scalars(select(Profile).where(Profile.org_id == oid).order_by(Profile.name)))


def _own_profile(db: Session, who: Principal, profile_id: str) -> Profile:
    prof = db.get(Profile, profile_id)
    if prof is None or (not who.is_superadmin and prof.org_id != who.org_id):
        raise HTTPException(404, "profile not found")
    return prof


@router.patch("/profiles/{profile_id}", response_model=s.ProfileOut, tags=["profiles"])
def update_profile(
    profile_id: str,
    body: s.ProfileUpdate,
    who: Principal = Depends(require("admin")),
    db: Session = Depends(get_db),
) -> Profile:
    prof = _own_profile(db, who, profile_id)
    audio = body.audio_settings if body.audio_settings is not None else prof.audio_settings
    turns = None if body.disable_turns else (body.turn_settings or prof.turn_settings)
    try:
        validate_profile(audio, turns)
    except ServiceError as exc:
        raise _svc(exc) from exc
    prof.audio_settings, prof.turn_settings = audio, turns
    if body.is_default:
        set_default_profile(db, prof.org_id, prof)
    elif body.is_default is False:
        prof.is_default = False
    audit(db, who, "profile.update", prof.org_id, profile_id=prof.id)
    return prof


@router.delete("/profiles/{profile_id}", status_code=204, tags=["profiles"])
def delete_profile(
    profile_id: str, who: Principal = Depends(require("admin")), db: Session = Depends(get_db)
) -> None:
    prof = _own_profile(db, who, profile_id)
    audit(db, who, "profile.delete", prof.org_id, profile_id=prof.id, name=prof.name)
    db.delete(prof)


# ---- session tokens (for browsers / mobile clients) -----------------------------------------


@router.post("/session-tokens", response_model=s.TokenOut, status_code=201, tags=["streaming"])
def create_session_token(
    body: s.TokenRequest,
    who: Principal = Depends(require("stream")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> s.TokenOut:
    if who.is_superadmin:
        raise HTTPException(422, "use an organization API key")
    assert who.org_id is not None
    try:
        org = get_org(db, who.org_id)
        prof = resolve_profile(db, org.id, body.profile)
    except ServiceError as exc:
        raise _svc(exc) from exc
    if body.mode == "relay":
        if not body.relay_target:
            raise HTTPException(422, "relay mode needs relay_target")
        try:
            check_relay_target(body.relay_target, org.relay_allowlist, settings.deployment_mode)
        except RelayTargetError as exc:
            raise HTTPException(422, str(exc)) from exc
    token, exp = mint_session_token(
        settings.secret_key,
        org_id=org.id,
        ttl_s=body.ttl_s or settings.session_token_ttl_s,
        mode=body.mode,
        profile_id=prof.id if prof else None,
        relay_target=body.relay_target,
        api_key_id=who.api_key_id,
    )
    path = "/v1/stream" if body.mode == "process" else "/v1/relay"
    return s.TokenOut(token=token, expires_at=exp, stream_url_path=f"{path}?token=<token>")


# ---- sessions, usage, audit -----------------------------------------------------------------


@router.get("/sessions", response_model=list[s.SessionOut], tags=["sessions"])
def list_sessions(
    org_id: str | None = None,
    status: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    who: Principal = Depends(require("usage:read")),
    db: Session = Depends(get_db),
) -> list[SessionRecord]:
    oid = org_for(who, org_id)
    q = select(SessionRecord).where(SessionRecord.org_id == oid)
    if status:
        q = q.where(SessionRecord.status == status)
    return list(db.scalars(q.order_by(SessionRecord.started_at.desc()).limit(limit)))


@router.get("/usage", response_model=s.UsageOut, tags=["usage"])
def get_usage(
    org_id: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    who: Principal = Depends(require("usage:read")),
    db: Session = Depends(get_db),
) -> s.UsageOut:
    oid = org_for(who, org_id)
    try:
        org = get_org(db, oid)
    except ServiceError as exc:
        raise _svc(exc) from exc
    end = (end or utcnow()).astimezone(UTC)
    start = (start or end - timedelta(days=30)).astimezone(UTC)
    days = usage_by_day(db, oid, start, end + timedelta(microseconds=1))
    return s.UsageOut(
        org_id=oid,
        period_start=start,
        period_end=end,
        audio_minutes=round(sum(d["audio_minutes"] for d in days), 3),
        sessions=sum(d["sessions"] for d in days),
        monthly_minutes_quota=org.monthly_minutes_quota,
        month_to_date_minutes=round(used_seconds(db, oid, month_start()) / 60.0, 3),
        days=days,
    )


@router.get("/audit", response_model=list[s.AuditOut], tags=["audit"])
def list_audit(
    org_id: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
    who: Principal = Depends(require("admin")),
    db: Session = Depends(get_db),
) -> list[AuditEvent]:
    oid = org_for(who, org_id)
    q = select(AuditEvent).where(AuditEvent.org_id == oid).order_by(AuditEvent.at.desc())
    return list(db.scalars(q.limit(limit)))


# ---- single sign-on members -----------------------------------------------------------------


@router.get("/sso/members", response_model=list[s.SsoMemberOut], tags=["sso"])
def list_sso_members(
    org_id: str | None = None,
    who: Principal = Depends(require("admin")),
    db: Session = Depends(get_db),
) -> list[SsoMember]:
    oid = org_for(who, org_id)
    return list(
        db.scalars(select(SsoMember).where(SsoMember.org_id == oid).order_by(SsoMember.email))
    )


@router.post("/sso/members", response_model=s.SsoMemberOut, status_code=201, tags=["sso"])
def add_sso_member(
    body: s.SsoMemberIn, who: Principal = Depends(require("admin")), db: Session = Depends(get_db)
) -> SsoMember:
    oid = org_for(who, body.org_id)
    email = body.email.strip().lower()
    if db.scalar(select(SsoMember).where(SsoMember.org_id == oid, SsoMember.email == email)):
        raise HTTPException(409, f"{email} is already a member")
    m = SsoMember(org_id=oid, email=email, role=body.role)
    db.add(m)
    db.flush()
    audit(db, who, "sso.member.add", oid, email=email, role=body.role)
    return m


@router.delete("/sso/members/{member_id}", status_code=204, tags=["sso"])
def remove_sso_member(
    member_id: str, who: Principal = Depends(require("admin")), db: Session = Depends(get_db)
) -> None:
    m = db.get(SsoMember, member_id)
    if m is None or (not who.is_superadmin and m.org_id != who.org_id):
        raise HTTPException(404, "member not found")
    audit(db, who, "sso.member.remove", m.org_id, email=m.email)
    db.delete(m)


# ---- billing --------------------------------------------------------------------------------


@router.get("/billing/reports", response_model=list[s.UsageReportOut], tags=["billing"])
def list_billing_reports(
    org_id: str | None = None,
    limit: int = Query(200, ge=1, le=5000),
    who: Principal = Depends(require("admin")),
    db: Session = Depends(get_db),
) -> list[UsageReport]:
    oid = org_for(who, org_id)
    q = select(UsageReport).where(UsageReport.org_id == oid, UsageReport.status != "empty")
    return list(db.scalars(q.order_by(UsageReport.period_start.desc()).limit(limit)))


# ---- exports (CSV / JSON Lines) ---------------------------------------------------------------


def _range(start: datetime | None, end: datetime | None) -> tuple[datetime, datetime]:
    end = (end or utcnow()).astimezone(UTC)
    start = (start or end - timedelta(days=31)).astimezone(UTC)
    if end - start > timedelta(days=400):
        raise HTTPException(422, "export at most 400 days at a time")
    return start, end


def _stream(
    rows: Iterator[dict[str, Any]], fmt: str, name: str, fields: list[str]
) -> StreamingResponse:
    def gen() -> Iterator[str]:
        if fmt == "csv":
            buf = io.StringIO()
            w = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow({k: _cell(r.get(k)) for k in fields})
                yield buf.getvalue()
                buf.seek(0)
                buf.truncate()
            yield buf.getvalue()
        else:
            for r in rows:
                yield json.dumps(r, default=str) + "\n"

    media = "text/csv" if fmt == "csv" else "application/x-ndjson"
    ext = "csv" if fmt == "csv" else "jsonl"
    return StreamingResponse(
        gen(),
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{name}.{ext}"'},
    )


def _cell(v: Any) -> Any:
    """CSV cell: JSON for structures; a leading ' stops spreadsheets running formulas."""
    if isinstance(v, dict | list):
        v = json.dumps(v, sort_keys=True)
    if isinstance(v, datetime):
        v = v.isoformat()
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r"):
        v = "'" + v
    return v


@router.get("/audit/export", tags=["audit"])
def export_audit(
    org_id: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    format: Literal["csv", "jsonl"] = "csv",
    who: Principal = Depends(require("admin")),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    oid = org_for(who, org_id)
    a, b = _range(start, end)
    items = list(
        db.scalars(
            select(AuditEvent)
            .where(AuditEvent.org_id == oid, AuditEvent.at >= a, AuditEvent.at < b)
            .order_by(AuditEvent.at)
        )
    )
    rows = (
        {"id": e.id, "at": e.at, "actor": e.actor, "action": e.action, "details": e.details}
        for e in items
    )
    audit(db, who, "audit.export", oid, start=a.isoformat(), end=b.isoformat(), rows=len(items))
    return _stream(rows, format, f"audit-{oid}", ["id", "at", "actor", "action", "details"])


SESSION_FIELDS = [
    "id",
    "started_at",
    "ended_at",
    "mode",
    "status",
    "audio_seconds",
    "profile_id",
    "api_key_id",
    "close_code",
    "close_reason",
    "event_counts",
    "quality",
]


@router.get("/sessions/export", tags=["sessions"])
def export_sessions(
    org_id: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    format: Literal["csv", "jsonl"] = "csv",
    who: Principal = Depends(require("usage:read")),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Every session (call) in the range by start time, for usage reconciliation."""
    oid = org_for(who, org_id)
    a, b = _range(start, end)
    items = list(
        db.scalars(
            select(SessionRecord)
            .where(SessionRecord.org_id == oid, SessionRecord.started_at >= a)
            .where(SessionRecord.started_at < b)
            .order_by(SessionRecord.started_at)
        )
    )
    rows = ({k: getattr(r, k) for k in SESSION_FIELDS} for r in items)
    return _stream(rows, format, f"sessions-{oid}", SESSION_FIELDS)


# registered last: "/sessions/export" must be matched before "/sessions/{session_id}"
@router.get("/sessions/{session_id}", response_model=s.SessionOut, tags=["sessions"])
def get_session(
    session_id: str, who: Principal = Depends(require("usage:read")), db: Session = Depends(get_db)
) -> SessionRecord:
    rec = db.get(SessionRecord, session_id)
    if rec is None or (not who.is_superadmin and rec.org_id != who.org_id):
        raise HTTPException(404, "session not found")
    return rec
