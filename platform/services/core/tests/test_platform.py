"""C7: platform owner bootstrap; the platform owner creates and lists organizations."""

import asyncio
import hashlib
import stat
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from nexora_core.app import create_app
from nexora_core.audit import verify_chain
from nexora_core.auth.csrf import CSRF_COOKIE, SESSION_COOKIE
from nexora_core.auth.sessions import create_session
from nexora_core.bootstrap import BOOTSTRAP_TOKEN_LIFETIME, bootstrap_platform_owner
from nexora_core.settings import Settings
from tests.db_harness import APP_ROLE, app_engine, as_role
from tests.mail_harness import FakeMailer

EMAIL = "owner@nexora.sa"
NOW = datetime(2026, 11, 14, 9, 0, tzinfo=UTC)


@pytest.fixture
async def fresh(migrated):
    owner = create_async_engine(migrated)
    async with owner.begin() as conn:
        await conn.execute(text("TRUNCATE organizations, users, password_resets CASCADE"))
    await owner.dispose()
    return migrated


async def run_bootstrap(url, token_file, email=EMAIL, now=NOW):
    engine = app_engine(url)
    try:
        return await bootstrap_platform_owner(engine, email=email, token_file=token_file, now=now)
    finally:
        await engine.dispose()


async def query(url, sql, **params):
    owner = create_async_engine(url)
    async with owner.connect() as conn:
        rows = (await conn.execute(text(sql), params)).all()
    await owner.dispose()
    return rows


def read_token(path) -> str:
    return next(line for line in path.read_text().splitlines() if line and not line.startswith("#"))


# --- bootstrap ---------------------------------------------------------------------------------


async def test_no_email_means_no_bootstrap(fresh, tmp_path):
    assert await run_bootstrap(fresh, tmp_path / "t", email="") is False
    assert await query(fresh, "SELECT 1 FROM users") == []
    assert not (tmp_path / "t").exists()


async def test_first_start_creates_owner_and_single_use_token_file(fresh, tmp_path):
    token_file = tmp_path / "secrets" / "owner-token"
    assert await run_bootstrap(fresh, token_file) is True
    [(uid, email, is_owner, pw)] = await query(
        fresh, "SELECT id, email, is_platform_owner, password_hash FROM users"
    )
    assert (email, is_owner, pw) == (EMAIL, True, None)  # no password is ever written to disk
    assert stat.S_IMODE(token_file.stat().st_mode) == 0o600
    assert stat.S_IMODE(token_file.parent.stat().st_mode) == 0o700
    token = read_token(token_file)
    assert len(token) >= 43
    [(stored, owner_id, expires)] = await query(
        fresh, "SELECT token_hash, user_id, expires_at FROM password_resets"
    )
    assert stored == hashlib.sha256(token.encode()).hexdigest()
    assert owner_id == uid
    assert expires == NOW + BOOTSTRAP_TOKEN_LIFETIME


async def test_restart_keeps_the_live_token(fresh, tmp_path):
    token_file = tmp_path / "owner-token"
    await run_bootstrap(fresh, token_file)
    first = token_file.read_text()
    assert await run_bootstrap(fresh, token_file, now=NOW + timedelta(hours=1)) is False
    assert token_file.read_text() == first
    assert len(await query(fresh, "SELECT 1 FROM users")) == 1
    assert len(await query(fresh, "SELECT 1 FROM password_resets")) == 1


async def test_expired_unused_token_is_reissued(fresh, tmp_path):
    token_file = tmp_path / "owner-token"
    await run_bootstrap(fresh, token_file)
    first = read_token(token_file)
    assert await run_bootstrap(fresh, token_file, now=NOW + BOOTSTRAP_TOKEN_LIFETIME + timedelta(seconds=1))
    assert read_token(token_file) != first
    assert len(await query(fresh, "SELECT 1 FROM users")) == 1


async def test_owner_with_a_password_gets_no_new_token(fresh, tmp_path):
    token_file = tmp_path / "owner-token"
    await run_bootstrap(fresh, token_file)
    token_file.unlink()
    owner = create_async_engine(fresh)
    async with owner.begin() as conn:
        await conn.execute(text("UPDATE users SET password_hash = 'set'"))
    await owner.dispose()
    assert await run_bootstrap(fresh, token_file, now=NOW + timedelta(days=3)) is False
    assert not token_file.exists()


async def test_existing_user_with_the_email_is_promoted(fresh, tmp_path):
    owner = create_async_engine(fresh)
    async with owner.begin() as conn:
        await conn.execute(
            text("INSERT INTO users (id, email, password_hash) VALUES ('usr_x', :e, 'h')"), {"e": EMAIL}
        )
    await owner.dispose()
    await run_bootstrap(fresh, tmp_path / "t")
    assert await query(fresh, "SELECT id, is_platform_owner FROM users") == [("usr_x", True)]
    assert not (tmp_path / "t").exists()  # already has a password


async def test_parallel_starts_create_one_owner(fresh, tmp_path):
    results = await asyncio.gather(*(run_bootstrap(fresh, tmp_path / "t") for _ in range(6)))
    assert results.count(True) == 1
    assert len(await query(fresh, "SELECT 1 FROM users WHERE is_platform_owner")) == 1


async def test_app_start_runs_the_bootstrap(fresh, tmp_path):
    token_file = tmp_path / "owner-token"
    app = create_app(
        Settings(
            environment="test",
            database_url=as_role(fresh, APP_ROLE),
            bootstrap_owner_email=EMAIL,
            bootstrap_token_file=str(token_file),
        )
    )
    async with app.router.lifespan_context(app):
        pass
    assert token_file.exists()


# --- platform organizations --------------------------------------------------------------------


@pytest.fixture
async def platform(fresh):
    owner = create_async_engine(fresh)
    async with owner.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO users (id, email, is_platform_owner) VALUES "
                "('usr_p', 'p@nexora.sa', true), ('usr_n', 'n@nexora.sa', false)"
            )
        )
    await owner.dispose()
    engine = app_engine(fresh)
    async with engine.begin() as conn:
        sessions = {
            u: await create_session(conn, user_id=u, now=datetime.now(UTC), ip=None, user_agent=None)
            for u in ("usr_p", "usr_n")
        }
    await engine.dispose()
    app = create_app(Settings(environment="test", database_url=as_role(fresh, APP_ROLE)))
    app.state.mailer = FakeMailer()
    yield app, sessions
    await app.state.engine.dispose()


def as_user(app, sessions, user):
    c = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://nexora.test")
    c.cookies.set(SESSION_COOKIE, sessions[user], domain="nexora.test")
    c.cookies.set(CSRF_COOKIE, "t", domain="nexora.test")
    c.headers["X-CSRF-Token"] = "t"
    return c


BODY = {"name": "Riyadh Health", "slug": "riyadh-health", "owner_email": "cto@riyadh-health.sa"}


async def test_create_organization_with_workspace_and_owner_invitation(platform, fresh):
    app, sessions = platform
    async with as_user(app, sessions, "usr_p") as c:
        r = await c.post("/v1/platform/organizations", json=BODY)
    assert r.status_code == 201, r.text
    body = r.json()
    org = body["id"]
    assert (body["name"], body["slug"]) == ("Riyadh Health", "riyadh-health")
    assert body["workspace"]["name"] == "Production"
    assert body["invitation"]["email"] == "cto@riyadh-health.sa"
    assert body["invitation"]["role"] == "org_owner"
    assert "token" not in str(body).lower()

    [(env, ws_org)] = await query(fresh, "SELECT environment, organization_id FROM workspaces")
    assert (env, ws_org) == ("production", org)
    [(role, ws, token_hash, expires, by)] = await query(
        fresh, "SELECT role_key, workspace_id, token_hash, expires_at, invited_by FROM invitations"
    )
    assert (role, ws, by) == ("org_owner", None, "usr_p")
    assert len(token_hash) == 64
    assert timedelta(days=6, hours=23) < expires - datetime.now(UTC) <= timedelta(days=7)

    actions = [
        a
        for (a,) in await query(
            fresh, "SELECT action FROM audit_logs WHERE organization_id = :o ORDER BY id", o=org
        )
    ]
    assert actions == ["organization.created", "workspace.created", "invitation.created"]
    engine = app_engine(fresh)
    async with engine.begin() as conn:
        await conn.execute(text("SELECT set_config('nexora.org_id', :o, true)"), {"o": org})
        assert (await verify_chain(conn, org)).ok
    await engine.dispose()


async def test_duplicate_slug_is_409(platform):
    app, sessions = platform
    async with as_user(app, sessions, "usr_p") as c:
        assert (await c.post("/v1/platform/organizations", json=BODY)).status_code == 201
        again = await c.post("/v1/platform/organizations", json={**BODY, "name": "Other"})
    assert again.status_code == 409
    assert again.json() == {"error": "slug_taken"}


@pytest.mark.parametrize(
    "bad",
    [{"slug": "Has Spaces"}, {"slug": "-edge"}, {"slug": "a"}, {"owner_email": "not-an-email"}, {"name": ""}],
)
async def test_invalid_input_is_422(platform, bad):
    app, sessions = platform
    async with as_user(app, sessions, "usr_p") as c:
        assert (await c.post("/v1/platform/organizations", json={**BODY, **bad})).status_code == 422


async def test_list_shows_every_organization(platform):
    app, sessions = platform
    async with as_user(app, sessions, "usr_p") as c:
        await c.post("/v1/platform/organizations", json=BODY)
        await c.post(
            "/v1/platform/organizations", json={**BODY, "slug": "jeddah-bank", "name": "Jeddah Bank"}
        )
        items = (await c.get("/v1/platform/organizations")).json()["items"]
    assert [(i["name"], i["members"]) for i in items] == [("Jeddah Bank", 0), ("Riyadh Health", 0)]


@pytest.mark.parametrize(("method", "json"), [("GET", None), ("POST", BODY)])
async def test_only_the_platform_owner(platform, method, json):
    app, sessions = platform
    async with as_user(app, sessions, "usr_n") as c:
        r = await c.request(method, "/v1/platform/organizations", json=json)
    assert r.status_code == 403
    assert r.json() == {"error": "forbidden", "missing_permission": "platform:organizations"}
