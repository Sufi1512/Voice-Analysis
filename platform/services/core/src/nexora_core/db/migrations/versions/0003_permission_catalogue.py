"""P1 C6: seed the permission catalogue; a narrow function to list a user's organizations.

The catalogue is a literal snapshot of ``nexora_core.authz.catalogue`` at this revision (a
migration must not change meaning when the code moves on); a test checks they match.

``nexora_user_organizations(user_id)`` is SECURITY DEFINER so the app role can list the
organizations a user belongs to without a BYPASSRLS connection. It returns only id, name,
slug and role for that user's memberships.

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

APP, ADMIN = "nexora_app", "nexora_admin"

PERMISSIONS = {
    "organization:read": "See the organization",
    "organization:update": "Rename the organization and change its settings",
    "workspace:read": "See workspaces",
    "workspace:create": "Create workspaces",
    "member:read": "See members and their roles",
    "member:invite": "Invite people",
    "member:manage": "Change members' roles and remove members",
    "audit:read": "Read the audit log",
    "platform:organizations": "Create and list all organizations (platform owner)",
}
READ = ["organization:read", "workspace:read", "member:read"]
ADMIN_PERMS = [
    *READ,
    "organization:update",
    "workspace:create",
    "member:invite",
    "member:manage",
    "audit:read",
]
GRANTS = {
    "platform_owner": ["platform:organizations"],
    "org_owner": ADMIN_PERMS,
    "org_admin": ADMIN_PERMS,
    "workspace_admin": [*READ, "member:invite"],
    "developer": READ,
    "operator": READ,
    "viewer": READ,
}


def upgrade() -> None:
    permissions = sa.table("permissions", sa.column("key"), sa.column("description"))
    role_permissions = sa.table("role_permissions", sa.column("role_key"), sa.column("permission_key"))
    op.bulk_insert(permissions, [{"key": k, "description": d} for k, d in PERMISSIONS.items()])
    op.bulk_insert(
        role_permissions, [{"role_key": r, "permission_key": p} for r, ps in GRANTS.items() for p in ps]
    )
    op.execute(
        "CREATE FUNCTION nexora_user_organizations(p_user_id text)"
        " RETURNS TABLE (id text, name text, slug text, role text)"
        " LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$"
        " SELECT DISTINCT ON (o.id) o.id, o.name, o.slug, m.role_key"
        " FROM memberships m JOIN organizations o ON o.id = m.organization_id"
        " JOIN roles r ON r.key = m.role_key"
        " WHERE m.user_id = p_user_id AND o.status = 'active'"
        " ORDER BY o.id, (m.workspace_id IS NULL) DESC, r.rank DESC $$"
    )
    op.execute("REVOKE ALL ON FUNCTION nexora_user_organizations(text) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION nexora_user_organizations(text) TO {APP}, {ADMIN}")


def downgrade() -> None:
    op.execute("DROP FUNCTION nexora_user_organizations(text)")
    op.execute("DELETE FROM role_permissions")
    op.execute("DELETE FROM permissions")
