"""P1 C7: list every organization for the platform owner without a BYPASSRLS connection.

``nexora_platform_organizations()`` is SECURITY DEFINER and returns only summary columns
(id, name, slug, status, created_at, member count). The API calls it only after checking
that the caller is the platform owner.

Revision ID: 0004
Revises: 0003
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

APP, ADMIN = "nexora_app", "nexora_admin"


def upgrade() -> None:
    op.execute(
        "CREATE FUNCTION nexora_platform_organizations()"
        " RETURNS TABLE (id text, name text, slug text, status text, created_at timestamptz, members bigint)"
        " LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$"
        " SELECT o.id, o.name, o.slug, o.status, o.created_at,"
        " (SELECT count(DISTINCT m.user_id) FROM memberships m WHERE m.organization_id = o.id)"
        " FROM organizations o WHERE o.status <> 'deleted' $$"
    )
    op.execute("REVOKE ALL ON FUNCTION nexora_platform_organizations() FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION nexora_platform_organizations() TO {APP}, {ADMIN}")


def downgrade() -> None:
    op.execute("DROP FUNCTION nexora_platform_organizations()")
