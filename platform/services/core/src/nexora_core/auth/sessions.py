"""Server-side sessions: 256-bit random id in the cookie, only its SHA-256 in the database."""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

IDLE_TIMEOUT = timedelta(hours=12)
ABSOLUTE_LIFETIME = timedelta(days=7)


@dataclass(frozen=True)
class Session:
    id_hash: str
    user_id: str
    mfa_passed_at: datetime | None
    active_organization_id: str | None
    expires_at: datetime


def hash_session_id(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


async def create_session(
    conn: AsyncConnection, *, user_id: str, now: datetime, ip: str | None, user_agent: str | None
) -> str:
    raw = secrets.token_urlsafe(32)
    await conn.execute(
        text(
            "INSERT INTO user_sessions"
            " (id_hash, user_id, created_at, last_seen_at, expires_at, ip, user_agent)"
            " VALUES (:h, :u, :now, :now, :exp, CAST(:ip AS inet), :ua)"
        ),
        {
            "h": hash_session_id(raw),
            "u": user_id,
            "now": now,
            "exp": now + ABSOLUTE_LIFETIME,
            "ip": ip,
            "ua": (user_agent or "")[:512],
        },
    )
    return raw


async def resolve_session(conn: AsyncConnection, raw: str, *, now: datetime) -> Session | None:
    """Return the live session for a cookie value and renew its idle window, or None."""
    row = (
        (
            await conn.execute(
                text(
                    "UPDATE user_sessions s SET last_seen_at = :now FROM users u"
                    " WHERE s.id_hash = :h AND u.id = s.user_id AND u.status = 'active'"
                    " AND s.revoked_at IS NULL AND s.expires_at > :now AND s.last_seen_at > :idle"
                    " RETURNING s.id_hash, s.user_id, s.mfa_passed_at, s.active_organization_id, s.expires_at"
                ),
                {"h": hash_session_id(raw), "now": now, "idle": now - IDLE_TIMEOUT},
            )
        )
        .mappings()
        .first()
    )
    return Session(**row) if row else None


async def revoke_session(conn: AsyncConnection, id_hash: str, *, now: datetime) -> None:
    await conn.execute(
        text("UPDATE user_sessions SET revoked_at = :now WHERE id_hash = :h AND revoked_at IS NULL"),
        {"h": id_hash, "now": now},
    )


async def revoke_all_sessions(conn: AsyncConnection, user_id: str, *, now: datetime) -> int:
    result = await conn.execute(
        text("UPDATE user_sessions SET revoked_at = :now WHERE user_id = :u AND revoked_at IS NULL"),
        {"u": user_id, "now": now},
    )
    return result.rowcount
