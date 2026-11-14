"""First platform owner: created on start from ``NEXORA_BOOTSTRAP_OWNER_EMAIL``.

No password is ever generated or written to disk. The owner is created without one, and a
single-use set-password token (24 h, SHA-256 in ``password_resets``) is written to a file
only its owner can read; the password reset flow consumes it. If the token expires unused,
the next start issues a new one. Parallel starts are serialised with an advisory lock.
"""

import contextlib
import os
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from nexora_core.ids import new_id
from nexora_core.logging import get_logger
from nexora_core.tokens import new_token

log = get_logger(__name__)
BOOTSTRAP_TOKEN_LIFETIME = timedelta(hours=24)


def _write_private(path: Path, content: str) -> None:
    if not path.parent.exists():
        path.parent.mkdir(parents=True, mode=0o700)
    tmp = path.with_name(f".{path.name}.tmp")
    with contextlib.suppress(FileNotFoundError):
        tmp.unlink()
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(content)
    tmp.replace(path)


async def _owner(conn: AsyncConnection, email: str) -> tuple[str, str | None, bool]:
    """(user id, password hash, changed) — creating or promoting the owner if needed."""
    row = (
        await conn.execute(
            text("SELECT id, password_hash FROM users WHERE is_platform_owner ORDER BY created_at LIMIT 1")
        )
    ).first()
    if row:
        return row[0], row[1], False
    existing = (
        await conn.execute(text("SELECT id, password_hash FROM users WHERE email = :e"), {"e": email})
    ).first()
    if existing:
        await conn.execute(
            text("UPDATE users SET is_platform_owner = true WHERE id = :i"), {"i": existing[0]}
        )
        log.warning("existing user promoted to platform owner", user_id=existing[0])
        return existing[0], existing[1], True
    uid = new_id("usr")
    await conn.execute(
        text("INSERT INTO users (id, email, is_platform_owner) VALUES (:i, :e, true)"), {"i": uid, "e": email}
    )
    log.info("platform owner created", user_id=uid)
    return uid, None, True


async def bootstrap_platform_owner(
    engine: AsyncEngine, *, email: str, token_file: Path, now: datetime
) -> bool:
    """Ensure a platform owner exists and can set a password. Returns True if anything changed."""
    email = email.strip()
    if not email:
        return False
    async with engine.begin() as conn:
        await conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('nexora:bootstrap-owner'))"))
        uid, password_hash, changed = await _owner(conn, email)
        if password_hash is not None:
            return changed
        live = await conn.scalar(
            text(
                "SELECT 1 FROM password_resets WHERE user_id = :u AND used_at IS NULL AND expires_at > :now"
            ),
            {"u": uid, "now": now},
        )
        if live:
            return changed
        raw, digest = new_token()
        expires = now + BOOTSTRAP_TOKEN_LIFETIME
        await conn.execute(
            text(
                "INSERT INTO password_resets (token_hash, user_id, expires_at, created_at)"
                " VALUES (:h, :u, :exp, :now)"
            ),
            {"h": digest, "u": uid, "exp": expires, "now": now},
        )
        _write_private(
            token_file,
            f"# NEXORA platform owner setup for {email}.\n"
            f"# Single use; expires {expires.isoformat()}.\n"
            "# Use it to set your password, then delete this file.\n"
            f"{raw}\n",
        )
        log.info(
            "platform owner set-password token written", path=str(token_file), expires_at=expires.isoformat()
        )
        return True
