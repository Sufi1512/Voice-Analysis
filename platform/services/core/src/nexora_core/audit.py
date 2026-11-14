"""Append-only audit log with a per-organization SHA-256 hash chain.

Each row's ``hash`` covers its own fields and the previous row's hash in the same
organization, so editing, deleting or inserting a row by hand breaks verification from that
row on. The service's database roles have no UPDATE or DELETE right on ``audit_logs``.
Writes for one organization are serialised with a transaction-scoped advisory lock (the
service role cannot lock audit rows, by design), so concurrent writes never fork the chain.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

GENESIS = ""
FORBIDDEN_DETAIL_KEYS = ("password", "token", "secret", "code", "otp")


@dataclass(frozen=True)
class ChainResult:
    ok: bool
    entries: int
    first_bad_id: int | None = None


def _digest(prev_hash: str, fields: dict[str, Any]) -> str:
    canonical = json.dumps(fields, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256((prev_hash + "\n" + canonical).encode()).hexdigest()


def _check_details(details: dict[str, Any]) -> None:
    for key in details:
        if any(word in key.lower() for word in FORBIDDEN_DETAIL_KEYS):
            raise ValueError(f"audit details must not carry {key!r} (passwords, tokens, codes, secrets)")


async def record(  # noqa: PLR0913 - one keyword per audit column
    conn: AsyncConnection,
    *,
    organization_id: str,
    actor_type: str,
    action: str,
    actor_id: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    workspace_id: str | None = None,
    details: dict[str, Any] | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> str:
    """Append one entry inside the caller's transaction; returns its hash."""
    details = details or {}
    _check_details(details)
    await conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('audit:' || :o))"), {"o": organization_id})
    prev = await conn.scalar(
        text("SELECT hash FROM audit_logs WHERE organization_id = :o ORDER BY id DESC LIMIT 1"),
        {"o": organization_id},
    )
    occurred_at = datetime.now(UTC)
    fields = {
        "organization_id": organization_id,
        "workspace_id": workspace_id,
        "actor_type": actor_type,
        "actor_id": actor_id,
        "action": action,
        "target_type": target_type,
        "target_id": target_id,
        "details": details,
        "occurred_at": occurred_at.isoformat(),
    }
    prev_hash = prev or GENESIS
    digest = _digest(prev_hash, fields)
    await conn.execute(
        text(
            "INSERT INTO audit_logs (organization_id, workspace_id, actor_type, actor_id, action,"
            " target_type, target_id, ip, user_agent, details, occurred_at, prev_hash, hash)"
            " VALUES (:organization_id, :workspace_id, :actor_type, :actor_id, :action, :target_type,"
            " :target_id, CAST(:ip AS inet), :user_agent, CAST(:details AS jsonb), :occurred_at,"
            " :prev_hash, :hash)"
        ),
        {
            **fields,
            "details": json.dumps(details),
            "occurred_at": occurred_at,
            "ip": ip,
            "user_agent": user_agent,
            "prev_hash": prev_hash,
            "hash": digest,
        },
    )
    return digest


async def verify_chain(conn: AsyncConnection, organization_id: str) -> ChainResult:
    """Recompute the organization's chain; report the first row that does not match."""
    rows = await conn.execute(
        text(
            "SELECT id, organization_id, workspace_id, actor_type, actor_id, action, target_type, target_id,"
            " details, occurred_at, prev_hash, hash FROM audit_logs WHERE organization_id = :o ORDER BY id"
        ),
        {"o": organization_id},
    )
    prev_hash, count = GENESIS, 0
    for row in rows.mappings():
        count += 1
        fields = {
            "organization_id": row["organization_id"],
            "workspace_id": row["workspace_id"],
            "actor_type": row["actor_type"],
            "actor_id": row["actor_id"],
            "action": row["action"],
            "target_type": row["target_type"],
            "target_id": row["target_id"],
            "details": row["details"],
            "occurred_at": row["occurred_at"].astimezone(UTC).isoformat(),
        }
        if row["prev_hash"] != prev_hash or row["hash"] != _digest(prev_hash, fields):
            return ChainResult(ok=False, entries=count, first_bad_id=row["id"])
        prev_hash = row["hash"]
    return ChainResult(ok=True, entries=count)
