"""The permission catalogue and what each system role grants (DB doc §3.2).

Only permissions that P1 endpoints check are listed; each later phase adds its own here and
in a migration (``test_database_catalogue_matches_code`` keeps the two in step).

Scope: an organization-wide membership grants its role's permissions everywhere in the
organization. A membership for one workspace grants ``WORKSPACE_MEMBER_PERMISSIONS`` at
organization level (enough to see the organization they belong to); workspace-level checks
arrive with the workspace endpoints.
"""

PERMISSIONS: dict[str, str] = {
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

_READ = frozenset({"organization:read", "workspace:read", "member:read"})
_ORG_ADMIN = frozenset(
    {
        *_READ,
        "organization:update",
        "workspace:create",
        "member:invite",
        "member:manage",
        "audit:read",
    }
)

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "platform_owner": frozenset({"platform:organizations"}),
    "org_owner": _ORG_ADMIN,
    "org_admin": _ORG_ADMIN,
    "workspace_admin": _READ | {"member:invite"},
    "developer": _READ,
    "operator": _READ,
    "viewer": _READ,
}

ROLES = tuple(ROLE_PERMISSIONS)
WORKSPACE_MEMBER_PERMISSIONS = frozenset({"organization:read"})
