"""P1 core: identity, tenancy, roles, audit log, secrets; row-level security.

Two database roles (created outside migrations, by deploy scripts or the test harness):

* ``nexora_app``: every authenticated request. Not a table owner, so row-level security
  applies. Each transaction sets ``nexora.org_id``; policies show only that organization.
* ``nexora_admin``: ``BYPASSRLS``. Only pre-login lookups (user by email, invitation and
  reset tokens) and platform-owner actions.

Global (not tenant-owned): users, user_identities, user_sessions, password_resets,
permissions, roles, role_permissions. Tenant-owned: everything with ``organization_id``.

Revision ID: 0001
Revises:
"""

from alembic import op

revision = "0001"
down_revision = None

APP, ADMIN = "nexora_app", "nexora_admin"
ORG = "current_setting('nexora.org_id', true)"

TENANT_TABLES = ("workspaces", "memberships", "invitations", "audit_logs", "secrets")

SCHEMA = """
CREATE EXTENSION IF NOT EXISTS citext;

CREATE TABLE organizations (
    id text PRIMARY KEY,
    name text NOT NULL,
    slug text NOT NULL UNIQUE,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended', 'deleted')),
    deployment_mode text NOT NULL DEFAULT 'dedicated' CHECK (deployment_mode IN ('shared', 'dedicated', 'on_prem')),
    data_region text NOT NULL DEFAULT 'sa',
    settings jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz
);

CREATE TABLE workspaces (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name text NOT NULL,
    slug text NOT NULL,
    environment text NOT NULL DEFAULT 'production' CHECK (environment IN ('development', 'staging', 'production')),
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('provisioning', 'active', 'failed', 'archived')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz,
    UNIQUE (organization_id, slug)
);

CREATE TABLE users (
    id text PRIMARY KEY,
    email citext NOT NULL UNIQUE,
    name text NOT NULL DEFAULT '',
    password_hash text,
    email_verified_at timestamptz,
    mfa_secret_id text,
    mfa_enabled_at timestamptz,
    is_platform_owner boolean NOT NULL DEFAULT false,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled')),
    last_login_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE user_identities (
    id text PRIMARY KEY,
    user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider text NOT NULL,
    subject text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (provider, subject)
);

CREATE TABLE user_sessions (
    id_hash text PRIMARY KEY,
    user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    mfa_passed_at timestamptz,
    active_organization_id text REFERENCES organizations(id) ON DELETE SET NULL,
    ip inet,
    user_agent text
);
CREATE INDEX user_sessions_user ON user_sessions (user_id) WHERE revoked_at IS NULL;

CREATE TABLE password_resets (
    token_hash text PRIMARY KEY,
    user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at timestamptz NOT NULL,
    used_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE permissions (key text PRIMARY KEY, description text NOT NULL DEFAULT '');

CREATE TABLE roles (
    key text PRIMARY KEY,
    name text NOT NULL,
    scope text NOT NULL CHECK (scope IN ('platform', 'organization', 'workspace')),
    rank int NOT NULL
);

CREATE TABLE role_permissions (
    role_key text NOT NULL REFERENCES roles(key) ON DELETE CASCADE,
    permission_key text NOT NULL REFERENCES permissions(key) ON DELETE CASCADE,
    PRIMARY KEY (role_key, permission_key)
);

CREATE TABLE memberships (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    workspace_id text REFERENCES workspaces(id) ON DELETE CASCADE,
    role_key text NOT NULL REFERENCES roles(key) DEFERRABLE INITIALLY DEFERRED,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE NULLS NOT DISTINCT (user_id, organization_id, workspace_id)
);

CREATE TABLE invitations (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    workspace_id text REFERENCES workspaces(id) ON DELETE CASCADE,
    email citext NOT NULL,
    role_key text NOT NULL REFERENCES roles(key) DEFERRABLE INITIALLY DEFERRED,
    token_hash text NOT NULL UNIQUE,
    expires_at timestamptz NOT NULL,
    accepted_at timestamptz,
    revoked_at timestamptz,
    invited_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE audit_logs (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    workspace_id text,
    actor_type text NOT NULL CHECK (actor_type IN ('user', 'api_key', 'system')),
    actor_id text,
    action text NOT NULL,
    target_type text,
    target_id text,
    ip inet,
    user_agent text,
    details jsonb NOT NULL DEFAULT '{}'::jsonb,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    prev_hash text NOT NULL,
    hash text NOT NULL
);
CREATE INDEX audit_logs_org_time ON audit_logs (organization_id, id);

CREATE TABLE secrets (
    id text PRIMARY KEY,
    organization_id text REFERENCES organizations(id) ON DELETE CASCADE,
    kind text NOT NULL,
    ciphertext bytea NOT NULL,
    wrapped_dek bytea NOT NULL,
    kek_id text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    rotated_at timestamptz
);
"""

# The seven system roles (P1 spec, DB doc §3.2). Rank: higher outranks lower.
SEED_ROLES = """
INSERT INTO roles (key, name, scope, rank) VALUES
    ('platform_owner', 'Platform owner', 'platform', 100),
    ('org_owner', 'Organization owner', 'organization', 90),
    ('org_admin', 'Organization admin', 'organization', 80),
    ('workspace_admin', 'Workspace admin', 'workspace', 70),
    ('developer', 'Developer', 'workspace', 50),
    ('operator', 'Operator', 'workspace', 40),
    ('viewer', 'Viewer', 'workspace', 10)
"""

POLICIES = f"""
ALTER TABLE organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE organizations FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant ON organizations USING (id = {ORG}) WITH CHECK (id = {ORG});
""" + "".join(
    f"""
ALTER TABLE {t} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {t} FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant ON {t} USING (organization_id = {ORG}) WITH CHECK (organization_id = {ORG});
"""
    for t in TENANT_TABLES
)

GRANTS = f"""
GRANT USAGE ON SCHEMA public TO {APP}, {ADMIN};
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP}, {ADMIN};
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {APP}, {ADMIN};
-- audit log is append-only for everyone the service uses
REVOKE UPDATE, DELETE ON audit_logs FROM {APP}, {ADMIN};
-- the catalogue is managed by migrations only
REVOKE INSERT, UPDATE, DELETE ON permissions, roles, role_permissions FROM {APP}, {ADMIN};
"""

DROP = """
DROP TABLE IF EXISTS secrets, audit_logs, invitations, memberships, role_permissions, roles, permissions,
    password_resets, user_sessions, user_identities, users, workspaces, organizations CASCADE;
"""


def _script(sql: str) -> None:
    """asyncpg runs one statement per call; none of ours contain a semicolon inside."""
    for statement in sql.split(";"):
        if statement.strip() and not all(
            line.strip().startswith("--") for line in statement.strip().splitlines()
        ):
            op.execute(statement)


def upgrade() -> None:
    _script(SCHEMA)
    _script(SEED_ROLES)
    _script(POLICIES)
    _script(GRANTS)


def downgrade() -> None:
    _script(DROP)
