"""C6: roles, permission catalogue, require(permission), RLS context (AC-1, AC-2)."""

from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from nexora_core.app import api_routes, create_app
from nexora_core.audit import record
from nexora_core.auth.csrf import CSRF_COOKIE, SESSION_COOKIE
from nexora_core.auth.sessions import create_session
from nexora_core.authz.catalogue import PERMISSIONS, ROLE_PERMISSIONS, ROLES, WORKSPACE_MEMBER_PERMISSIONS
from nexora_core.authz.require import route_permission
from nexora_core.settings import Settings
from tests.db_harness import APP_ROLE, app_engine, as_role

ORG_ROLES = ["org_owner", "org_admin", "workspace_admin", "developer", "operator", "viewer"]
# A valid body for every protected route, so "allowed" means the handler ran.
BODIES = {("PATCH", "/v1/organizations/{org}"): {"name": "Org A"}}


@pytest.fixture(scope="module")
async def world(migrated):
    """org_a with one org-wide member per role, a workspace-only viewer; org_b with its own owner."""
    owner = create_async_engine(migrated)
    async with owner.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO organizations (id, name, slug) VALUES "
                "('org_a','Org A','org-a'),('org_b','Org B','org-b')"
            )
        )
        await conn.execute(
            text(
                "INSERT INTO workspaces (id, organization_id, name, slug) VALUES "
                "('ws_a1','org_a','Production','production')"
            )
        )
        users = [*(f"usr_{r}" for r in ORG_ROLES), "usr_ws_viewer", "usr_b_owner", "usr_platform", "usr_none"]
        for u in users:
            await conn.execute(
                text("INSERT INTO users (id, email, is_platform_owner) VALUES (:u, :e, :p)"),
                {"u": u, "e": f"{u}@example.sa", "p": u == "usr_platform"},
            )
        for r in ORG_ROLES:
            await conn.execute(
                text(
                    "INSERT INTO memberships (id, organization_id, user_id, role_key) "
                    "VALUES (:i, 'org_a', :u, :r)"
                ),
                {"i": f"mem_{r}", "u": f"usr_{r}", "r": r},
            )
        await conn.execute(
            text(
                "INSERT INTO memberships (id, organization_id, user_id, workspace_id, role_key) "
                "VALUES ('mem_wsv','org_a','usr_ws_viewer','ws_a1','viewer'),"
                " ('mem_bo','org_b','usr_b_owner',NULL,'org_owner')"
            )
        )
    await owner.dispose()
    engine = app_engine(migrated)
    sessions = {}
    async with engine.begin() as conn:
        for u in users:
            sessions[u] = await create_session(
                conn, user_id=u, now=datetime.now(UTC), ip=None, user_agent=None
            )
        await conn.execute(text("SELECT set_config('nexora.org_id', 'org_b', true)"))
        await record(conn, organization_id="org_b", actor_type="system", action="org.secret_b")
    await engine.dispose()
    return sessions


@pytest.fixture
async def app(migrated, world):
    application = create_app(Settings(environment="test", database_url=as_role(migrated, APP_ROLE)))
    yield application
    await application.state.engine.dispose()


def as_user(app, sessions, user: str) -> httpx.AsyncClient:
    c = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://nexora.test")
    c.cookies.set(SESSION_COOKIE, sessions[user], domain="nexora.test")
    c.cookies.set(CSRF_COOKIE, "t", domain="nexora.test")
    c.headers["X-CSRF-Token"] = "t"
    return c


def protected_routes(app) -> list[tuple[str, str, str]]:
    return [
        (m, route.path, perm)
        for route in api_routes(app)
        if (perm := route_permission(route))
        for m in sorted(route.methods)
    ]


# --- catalogue ---------------------------------------------------------------------------------


def test_seven_roles_and_every_granted_permission_is_catalogued():
    assert set(ROLES) == {"platform_owner", *ORG_ROLES}
    for perms in ROLE_PERMISSIONS.values():
        assert perms <= PERMISSIONS.keys()
    assert PERMISSIONS.keys() >= WORKSPACE_MEMBER_PERMISSIONS
    assert ROLE_PERMISSIONS["viewer"] <= ROLE_PERMISSIONS["operator"] <= ROLE_PERMISSIONS["developer"]
    assert ROLE_PERMISSIONS["org_admin"] <= ROLE_PERMISSIONS["org_owner"]


async def test_database_catalogue_matches_code(migrated):
    owner = create_async_engine(migrated)
    async with owner.connect() as conn:
        db_perms = set((await conn.execute(text("SELECT key FROM permissions"))).scalars())
        pairs = (await conn.execute(text("SELECT role_key, permission_key FROM role_permissions"))).all()
    await owner.dispose()
    assert db_perms == set(PERMISSIONS)
    assert {(r, p) for r, p in pairs} == {(r, p) for r, ps in ROLE_PERMISSIONS.items() for p in ps}


def test_every_organization_route_declares_a_permission(app):
    for route in api_routes(app):
        if "{org}" in route.path:
            assert route_permission(route), f"{route.path} has no require(permission)"
    assert protected_routes(app), "no protected routes found"


# --- the matrix (AC-2) -------------------------------------------------------------------------


def matrix_cases():
    app = create_app(Settings(environment="test", database_url="postgresql+asyncpg://unused/x"))
    cases = []
    for method, path, perm in protected_routes(app):
        cases.extend(
            (method, path, perm, f"usr_{role}", perm in ROLE_PERMISSIONS[role]) for role in ORG_ROLES
        )
        cases.append((method, path, perm, "usr_ws_viewer", perm in WORKSPACE_MEMBER_PERMISSIONS))
        cases.append((method, path, perm, "usr_platform", True))
    return cases


@pytest.mark.parametrize(("method", "path", "perm", "user", "allowed"), matrix_cases())
async def test_endpoint_role_matrix(app, world, method, path, perm, user, allowed):
    async with as_user(app, world, user) as c:
        r = await c.request(method, path.replace("{org}", "org_a"), json=BODIES.get((method, path)))
    if allowed:
        assert r.status_code < 400, r.text
    else:
        assert r.status_code == 403
        assert r.json() == {"error": "forbidden", "missing_permission": perm}


@pytest.mark.parametrize("user", ["usr_none", "usr_b_owner"])
@pytest.mark.parametrize("org", ["org_a", "org_missing"])
async def test_non_members_get_404_whether_or_not_the_org_exists(app, world, user, org):
    async with as_user(app, world, user) as c:
        r = await c.get(f"/v1/organizations/{org}")
    assert r.status_code == 404
    assert r.json() == {"error": "not_found"}


async def test_platform_owner_gets_404_for_a_missing_org(app, world):
    async with as_user(app, world, "usr_platform") as c:
        assert (await c.get("/v1/organizations/org_missing")).status_code == 404


async def test_unauthenticated_is_401(app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://nexora.test") as c:
        assert (await c.get("/v1/organizations/org_a")).status_code == 401


# --- behaviour behind the checks ---------------------------------------------------------------


async def test_role_change_takes_effect_on_the_next_request(app, world, migrated):
    async with as_user(app, world, "usr_viewer") as c:
        assert (await c.patch("/v1/organizations/org_a", json={"name": "X"})).status_code == 403
        owner = create_async_engine(migrated)
        async with owner.begin() as conn:
            await conn.execute(text("UPDATE memberships SET role_key = 'org_admin' WHERE id = 'mem_viewer'"))
        try:
            assert (await c.patch("/v1/organizations/org_a", json={"name": "Org A"})).status_code == 200
        finally:
            async with owner.begin() as conn:
                await conn.execute(text("UPDATE memberships SET role_key = 'viewer' WHERE id = 'mem_viewer'"))
            await owner.dispose()


async def test_my_organizations_lists_only_mine(app, world):
    async with as_user(app, world, "usr_viewer") as c:
        assert (await c.get("/v1/organizations")).json() == {
            "items": [{"id": "org_a", "name": "Org A", "slug": "org-a", "role": "viewer"}]
        }
    async with as_user(app, world, "usr_none") as c:
        assert (await c.get("/v1/organizations")).json() == {"items": []}


async def test_update_writes_an_audit_row_in_that_org_only(app, world):
    async with as_user(app, world, "usr_org_owner") as c:
        assert (await c.patch("/v1/organizations/org_a", json={"name": "Org A"})).status_code == 200
        logs = (await c.get("/v1/organizations/org_a/audit-logs")).json()["items"]
    actions = [e["action"] for e in logs]
    assert "organization.updated" in actions
    assert "org.secret_b" not in actions  # RLS: org_b's history is invisible from org_a
    entry = next(e for e in logs if e["action"] == "organization.updated")
    assert entry["actor_id"] == "usr_org_owner"
    assert entry["details"] == {"fields": ["name"]}


async def test_update_validates_input(app, world):
    async with as_user(app, world, "usr_org_owner") as c:
        assert (await c.patch("/v1/organizations/org_a", json={"name": ""})).status_code == 422
