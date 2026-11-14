"""C8: SMTP email; invitations (Viewer default, 7 days, single use); acceptance (AC-3, AC-4d, AC-5)."""

import asyncio
import hashlib
import os
import re
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from nexora_core.app import create_app
from nexora_core.audit import verify_chain
from nexora_core.auth.csrf import CSRF_COOKIE, SESSION_COOKIE
from nexora_core.auth.passwords import hash_password
from nexora_core.auth.sessions import create_session
from nexora_core.settings import Settings
from tests.db_harness import APP_ROLE, app_engine, as_role
from tests.mail_harness import free_port, start_smtp

PORTAL = "https://portal.nexora.test"
LINK = re.compile(re.escape(PORTAL) + r"/invite#([A-Za-z0-9_-]{43,})")
EXISTING_PASSWORD = "existing user password"
NEW_PASSWORD = "a long new password"


@pytest.fixture(scope="module")
def smtp():
    controller, inbox = start_smtp()
    yield controller, inbox
    controller.stop()


@pytest.fixture(scope="module")
async def world(migrated):
    owner = create_async_engine(migrated)
    async with owner.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO organizations (id, name, slug) VALUES ('org_a', 'Org A', 'org-a'),"
                " ('org_b', 'Org B', 'org-b')"
            )
        )
        await conn.execute(
            text(
                "INSERT INTO workspaces (id, organization_id, name, slug) VALUES "
                "('ws_a1', 'org_a', 'Production', 'production'), ('ws_b1', 'org_b', 'P', 'p')"
            )
        )
        for u, role in (
            ("usr_owner", "org_owner"),
            ("usr_admin", "org_admin"),
            ("usr_wsadmin", "workspace_admin"),
            ("usr_viewer", "viewer"),
        ):
            await conn.execute(
                text("INSERT INTO users (id, email) VALUES (:u, :e)"), {"u": u, "e": f"{u}@a.sa"}
            )
            await conn.execute(
                text(
                    "INSERT INTO memberships (id, organization_id, user_id, role_key)"
                    " VALUES (:i, 'org_a', :u, :r)"
                ),
                {"i": f"mem_{u}", "u": u, "r": role},
            )
        await conn.execute(
            text(
                "INSERT INTO users (id, email, password_hash, email_verified_at)"
                " VALUES ('usr_exist', 'exist@b.sa', :h, now())"
            ),
            {"h": hash_password(EXISTING_PASSWORD)},
        )
    await owner.dispose()
    engine = app_engine(migrated)
    async with engine.begin() as conn:
        sessions = {
            u: await create_session(conn, user_id=u, now=datetime.now(UTC), ip=None, user_agent=None)
            for u in ("usr_owner", "usr_admin", "usr_wsadmin", "usr_viewer", "usr_exist")
        }
    await engine.dispose()
    return sessions


def make_app(migrated, smtp_port):
    return create_app(
        Settings(
            environment="test",
            database_url=as_role(migrated, APP_ROLE),
            smtp_host="127.0.0.1",
            smtp_port=smtp_port,
            smtp_from="NEXORA <no-reply@nexora.test>",
            public_url=PORTAL,
        )
    )


@pytest.fixture
async def app(migrated, world, smtp):
    controller, inbox = smtp
    inbox.messages.clear()
    owner = create_async_engine(migrated)
    async with owner.begin() as conn:
        await conn.execute(text("DELETE FROM invitations"))
        await conn.execute(
            text(
                "DELETE FROM memberships WHERE user_id NOT IN "
                "('usr_owner', 'usr_admin', 'usr_wsadmin', 'usr_viewer')"
            )
        )
        await conn.execute(text("DELETE FROM users WHERE email LIKE 'new%'"))
    await owner.dispose()
    application = make_app(migrated, controller.port)
    yield application
    await application.state.engine.dispose()


def client(app, sessions=None, user=None) -> httpx.AsyncClient:
    c = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://nexora.test")
    if user:
        c.cookies.set(SESSION_COOKIE, sessions[user], domain="nexora.test")
    c.cookies.set(CSRF_COOKIE, "t", domain="nexora.test")

    async def echo_csrf(request: httpx.Request) -> None:  # like the portal: send the current cookie
        request.headers["X-CSRF-Token"] = c.cookies.get(CSRF_COOKIE, "")

    c.event_hooks["request"].append(echo_csrf)
    return c


async def invite(app, world, body, user="usr_owner") -> httpx.Response:
    async with client(app, world, user) as c:
        return await c.post("/v1/organizations/org_a/invitations", json=body)


def token_from(inbox, to: str) -> str:
    msg = next(m for m in reversed(inbox.messages) if m["X-Envelope-To"] == to)
    return LINK.search(msg.get_content()).group(1)


async def query(url, sql, **params):
    owner = create_async_engine(url)
    async with owner.connect() as conn:
        rows = (await conn.execute(text(sql), params)).all()
    await owner.dispose()
    return rows


# --- creating invitations ----------------------------------------------------------------------


async def test_invite_defaults_to_viewer_and_emails_a_link(app, world, smtp, migrated):
    _, inbox = smtp
    r = await invite(app, world, {"email": "new1@x.sa"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert (body["role"], body["workspace_id"], body["email"]) == ("viewer", None, "new1@x.sa")
    assert "token" not in r.text.lower()
    [msg] = inbox.messages
    assert msg["X-Envelope-To"] == "new1@x.sa"
    assert msg["From"] == "NEXORA <no-reply@nexora.test>"
    assert "Org A" in msg["Subject"]
    token = token_from(inbox, "new1@x.sa")
    [(stored, role)] = await query(migrated, "SELECT token_hash, role_key FROM invitations")
    assert stored == hashlib.sha256(token.encode()).hexdigest()
    assert role == "viewer"


async def test_cannot_invite_above_your_own_role(app, world):
    r = await invite(app, world, {"email": "new2@x.sa", "role": "org_owner"}, user="usr_admin")
    assert r.status_code == 403
    assert r.json() == {"error": "role_too_high"}
    assert (
        await invite(app, world, {"email": "new2@x.sa", "role": "org_admin"}, user="usr_admin")
    ).status_code == 201
    assert (await invite(app, world, {"email": "new3@x.sa", "role": "org_owner"})).status_code == 201


@pytest.mark.parametrize("role", ["platform_owner", "superuser"])
async def test_unknown_or_platform_roles_are_refused(app, world, role):
    assert (await invite(app, world, {"email": "new4@x.sa", "role": role})).status_code == 422


async def test_organization_roles_cannot_be_workspace_scoped(app, world):
    r = await invite(app, world, {"email": "new5@x.sa", "role": "org_admin", "workspace_id": "ws_a1"})
    assert r.status_code == 422


async def test_workspace_admins_invite_into_a_workspace_only(app, world):
    r = await invite(app, world, {"email": "new6@x.sa"}, user="usr_wsadmin")
    assert r.status_code == 403
    assert r.json() == {"error": "workspace_required"}
    ok = await invite(
        app, world, {"email": "new6@x.sa", "role": "developer", "workspace_id": "ws_a1"}, user="usr_wsadmin"
    )
    assert ok.status_code == 201


@pytest.mark.parametrize("ws", ["ws_b1", "ws_missing"])  # another organization's workspace is invisible
async def test_workspace_must_belong_to_the_organization(app, world, ws):
    r = await invite(app, world, {"email": "new7@x.sa", "workspace_id": ws})
    assert r.status_code == 422
    assert r.json() == {"error": "unknown_workspace"}


async def test_existing_member_is_409(app, world):
    r = await invite(app, world, {"email": "usr_viewer@a.sa"})
    assert r.status_code == 409
    assert r.json() == {"error": "already_member"}


async def test_reinviting_replaces_the_pending_invitation(app, world, smtp):
    _, inbox = smtp
    await invite(app, world, {"email": "new8@x.sa"})
    first = token_from(inbox, "new8@x.sa")
    await invite(app, world, {"email": "new8@x.sa", "role": "developer"})
    second = token_from(inbox, "new8@x.sa")
    async with client(app) as c:
        old = await c.post(f"/v1/invitations/{first}/accept", json={"password": NEW_PASSWORD})
        assert old.status_code == 410
        assert old.json() == {"error": "invitation_used"}
        assert (
            await c.post(f"/v1/invitations/{second}/accept", json={"password": NEW_PASSWORD})
        ).status_code == 200


async def test_email_failure_leaves_no_invitation(migrated, world, smtp):
    app = make_app(migrated, free_port())  # nothing listens there
    try:
        r = await invite(app, world, {"email": "new9@x.sa"})
    finally:
        await app.state.engine.dispose()
    assert r.status_code == 502
    assert r.json() == {"error": "email_failed"}
    assert await query(migrated, "SELECT 1 FROM invitations WHERE email = 'new9@x.sa'") == []


async def test_header_injection_through_the_organization_name(app, world, smtp, migrated):
    _, inbox = smtp
    owner = create_async_engine(migrated)
    async with owner.begin() as conn:
        await conn.execute(
            text("UPDATE organizations SET name = E'Evil\\r\\nBcc: spy@evil.sa' WHERE id = 'org_a'")
        )
    try:
        assert (await invite(app, world, {"email": "new10@x.sa"})).status_code == 201
    finally:
        async with owner.begin() as conn:
            await conn.execute(text("UPDATE organizations SET name = 'Org A' WHERE id = 'org_a'"))
        await owner.dispose()
    [msg] = inbox.messages
    assert msg["Bcc"] is None
    assert msg["X-Envelope-To"] == "new10@x.sa"


# --- accepting ---------------------------------------------------------------------------------


async def test_new_user_accepts_sets_password_and_is_signed_in(app, world, smtp, migrated):
    _, inbox = smtp
    await invite(app, world, {"email": "new11@x.sa", "role": "developer", "workspace_id": "ws_a1"})
    token = token_from(inbox, "new11@x.sa")
    async with client(app) as c:
        r = await c.post(f"/v1/invitations/{token}/accept", json={"password": NEW_PASSWORD, "name": "Noura"})
        assert r.status_code == 200, r.text
        assert r.json()["organization_id"] == "org_a"
        assert SESSION_COOKIE in c.cookies
        me = (await c.get("/v1/me")).json()
        assert me["user"]["email"] == "new11@x.sa"
        assert me["user"]["name"] == "Noura"
    [(role, ws, verified, pw)] = await query(
        migrated,
        "SELECT m.role_key, m.workspace_id, u.email_verified_at, u.password_hash FROM memberships m"
        " JOIN users u ON u.id = m.user_id WHERE u.email = 'new11@x.sa'",
    )
    assert (role, ws) == ("developer", "ws_a1")
    assert verified is not None
    assert pw.startswith("$argon2id$")
    actions = [
        a for (a,) in await query(migrated, "SELECT action FROM audit_logs WHERE organization_id='org_a'")
    ]
    assert actions[-2:] == ["invitation.accepted", "member.added"]
    engine = app_engine(migrated)
    async with engine.begin() as conn:
        await conn.execute(text("SELECT set_config('nexora.org_id', 'org_a', true)"))
        assert (await verify_chain(conn, "org_a")).ok
    await engine.dispose()


async def test_an_invitation_works_once(app, world, smtp):
    _, inbox = smtp
    await invite(app, world, {"email": "new12@x.sa"})
    token = token_from(inbox, "new12@x.sa")
    async with client(app) as c:
        assert (
            await c.post(f"/v1/invitations/{token}/accept", json={"password": NEW_PASSWORD})
        ).status_code == 200
        again = await c.post(f"/v1/invitations/{token}/accept", json={"password": NEW_PASSWORD})
    assert again.status_code == 410
    assert again.json() == {"error": "invitation_used"}


async def test_expired_invitation_is_refused(app, world, smtp, migrated):
    _, inbox = smtp
    await invite(app, world, {"email": "new13@x.sa"})
    token = token_from(inbox, "new13@x.sa")
    owner = create_async_engine(migrated)
    async with owner.begin() as conn:
        await conn.execute(text("UPDATE invitations SET expires_at = now() - interval '1 second'"))
    await owner.dispose()
    async with client(app) as c:
        r = await c.post(f"/v1/invitations/{token}/accept", json={"password": NEW_PASSWORD})
    assert r.status_code == 410
    assert r.json() == {"error": "invitation_expired"}


async def test_unknown_token_is_404(app):
    async with client(app) as c:
        r = await c.post("/v1/invitations/" + "A" * 43 + "/accept", json={"password": NEW_PASSWORD})
    assert r.status_code == 404
    assert r.json() == {"error": "invitation_invalid"}


@pytest.mark.parametrize("password", ["", "short-pass"])
async def test_new_users_need_a_12_character_password(app, world, smtp, password):
    _, inbox = smtp
    await invite(app, world, {"email": "new14@x.sa"})
    token = token_from(inbox, "new14@x.sa")
    async with client(app) as c:
        r = await c.post(f"/v1/invitations/{token}/accept", json={"password": password})
    assert r.status_code == 422


async def test_existing_user_confirms_with_their_password(app, world, smtp, migrated):
    _, inbox = smtp
    await invite(app, world, {"email": "exist@b.sa"})
    token = token_from(inbox, "exist@b.sa")
    async with client(app) as c:
        wrong = await c.post(f"/v1/invitations/{token}/accept", json={"password": "not their password"})
        assert wrong.status_code == 401
        assert wrong.json() == {"error": "invalid_credentials"}
        assert (
            await c.post(f"/v1/invitations/{token}/accept", json={"password": EXISTING_PASSWORD})
        ).status_code == 200
    [(role,)] = await query(migrated, "SELECT role_key FROM memberships WHERE user_id = 'usr_exist'")
    assert role == "viewer"


async def test_existing_user_signed_in_needs_no_password(app, world, smtp):
    _, inbox = smtp
    await invite(app, world, {"email": "exist@b.sa"})
    token = token_from(inbox, "exist@b.sa")
    async with client(app, world, "usr_exist") as c:
        assert (await c.post(f"/v1/invitations/{token}/accept", json={})).status_code == 200


async def test_signed_in_as_someone_else_is_refused(app, world, smtp):
    _, inbox = smtp
    await invite(app, world, {"email": "exist@b.sa"})
    token = token_from(inbox, "exist@b.sa")
    async with client(app, world, "usr_viewer") as c:
        r = await c.post(f"/v1/invitations/{token}/accept", json={})
    assert r.status_code == 403
    assert r.json() == {"error": "invitation_for_another_account"}


# --- platform flow -----------------------------------------------------------------------------


async def test_platform_created_organization_emails_its_first_owner(migrated, smtp):
    controller, inbox = smtp
    inbox.messages.clear()
    owner = create_async_engine(migrated)
    async with owner.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO users (id, email, is_platform_owner) VALUES ('usr_p', 'p@n.sa', true)"
                " ON CONFLICT DO NOTHING"
            )
        )
    await owner.dispose()
    engine = app_engine(migrated)
    async with engine.begin() as conn:
        raw = await create_session(conn, user_id="usr_p", now=datetime.now(UTC), ip=None, user_agent=None)
    await engine.dispose()
    app = make_app(migrated, controller.port)
    try:
        async with client(app, {"usr_p": raw}, "usr_p") as c:
            r = await c.post(
                "/v1/platform/organizations",
                json={"name": "Dammam Energy", "slug": "dammam-energy", "owner_email": "new-ceo@de.sa"},
            )
            assert r.status_code == 201
            token = token_from(inbox, "new-ceo@de.sa")
            accepted = await c.post(f"/v1/invitations/{token}/accept", json={"password": NEW_PASSWORD})
            assert accepted.status_code == 403  # signed in as the platform owner, not the invitee
        async with client(app) as fresh:
            assert (
                await fresh.post(f"/v1/invitations/{token}/accept", json={"password": NEW_PASSWORD})
            ).status_code == 200
    finally:
        await app.state.engine.dispose()


@pytest.mark.skipif(not os.environ.get("NEXORA_TEST_MAILPIT"), reason="needs Mailpit (CI service)")
async def test_delivery_through_mailpit(app, world, migrated):
    base = os.environ["NEXORA_TEST_MAILPIT"]  # e.g. http://localhost:8025
    app.state.mailer.settings = app.state.settings.model_copy(
        update={"smtp_host": "127.0.0.1", "smtp_port": 1025}
    )
    assert (await invite(app, world, {"email": "new-mailpit@x.sa"})).status_code == 201
    async with httpx.AsyncClient() as http:
        found = (await http.get(f"{base}/api/v1/search", params={"query": "to:new-mailpit@x.sa"})).json()
    assert len(found["messages"]) >= 1


async def test_two_simultaneous_acceptances_one_wins(app, world, smtp, migrated):
    _, inbox = smtp
    await invite(app, world, {"email": "new15@x.sa"})
    token = token_from(inbox, "new15@x.sa")

    async def attempt() -> int:
        async with client(app) as c:
            return (
                await c.post(f"/v1/invitations/{token}/accept", json={"password": NEW_PASSWORD})
            ).status_code

    results = sorted(await asyncio.gather(*(attempt() for _ in range(4))))
    assert results.count(200) == 1
    assert len(await query(migrated, "SELECT 1 FROM users WHERE email = 'new15@x.sa'")) == 1
