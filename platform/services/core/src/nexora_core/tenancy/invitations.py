"""Invitations: 7 days, single use, token stored as SHA-256 (the raw token is emailed)."""

from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from nexora_core.ids import new_id
from nexora_core.tokens import new_token

INVITATION_LIFETIME = timedelta(days=7)
DEFAULT_ROLE = "viewer"


async def create_invitation(  # noqa: PLR0913 - one keyword per invitation field
    conn: AsyncConnection,
    *,
    organization_id: str,
    email: str,
    invited_by: str,
    now: datetime,
    role: str = DEFAULT_ROLE,
    workspace_id: str | None = None,
) -> tuple[dict, str]:
    """Insert an invitation in the caller's transaction (``nexora.org_id`` must be set).

    Returns the stored fields and the raw token for the email.
    """
    raw, digest = new_token()
    row = {
        "id": new_id("inv"),
        "organization_id": organization_id,
        "workspace_id": workspace_id,
        "email": email.strip(),
        "role_key": role,
        "expires_at": now + INVITATION_LIFETIME,
        "invited_by": invited_by,
    }
    await conn.execute(
        text(
            "INSERT INTO invitations (id, organization_id, workspace_id, email, role_key, token_hash,"
            " expires_at, invited_by, created_at) VALUES (:id, :organization_id, :workspace_id, :email,"
            " :role_key, :token_hash, :expires_at, :invited_by, :now)"
        ),
        {**row, "token_hash": digest, "now": now},
    )
    return row, raw
