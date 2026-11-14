"""P1 C8: find an invitation by token before the organization is known.

``nexora_invitation_by_token(token_hash)`` is SECURITY DEFINER and returns one invitation
(plus its organization's name) for an exact SHA-256 match, so accepting an invitation needs
no BYPASSRLS connection. Knowing the hash requires the 256-bit token from the email.

Revision ID: 0005
Revises: 0004
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

APP, ADMIN = "nexora_app", "nexora_admin"


def upgrade() -> None:
    op.execute(
        "CREATE FUNCTION nexora_invitation_by_token(p_token_hash text)"
        " RETURNS TABLE (id text, organization_id text, organization_name text, workspace_id text,"
        " email citext, role_key text, expires_at timestamptz, accepted_at timestamptz,"
        " revoked_at timestamptz)"
        " LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$"
        " SELECT i.id, i.organization_id, o.name, i.workspace_id, i.email, i.role_key, i.expires_at,"
        " i.accepted_at, i.revoked_at FROM invitations i JOIN organizations o ON o.id = i.organization_id"
        " WHERE i.token_hash = p_token_hash AND o.status = 'active' $$"
    )
    op.execute("REVOKE ALL ON FUNCTION nexora_invitation_by_token(text) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION nexora_invitation_by_token(text) TO {APP}, {ADMIN}")


def downgrade() -> None:
    op.execute("DROP FUNCTION nexora_invitation_by_token(text)")
