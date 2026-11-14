"""C5: passwords, server-side sessions, login, logout, logout everywhere, lockout, CSRF (AC-3)."""

import hashlib
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from nexora_core.app import create_app
from nexora_core.auth.passwords import hash_password, verify_password
from nexora_core.settings import Settings
from tests.db_harness import APP_ROLE, as_role

SESSION, CSRF = "__Host-nexora_session", "__Host-nexora_csrf"
PASSWORD = "correct horse battery staple"


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 14, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kw: float) -> None:
        self.now += timedelta(**kw)


@pytest.fixture(scope="module")
async def users(migrated):
    owner = create_async_engine(migrated)
    hashed = hash_password(PASSWORD)
    async with owner.begin() as conn:
        for uid, email, status in (
            ("usr_a", "ada@example.sa", "active"),
            ("usr_d", "dis@example.sa", "disabled"),
        ):
            await conn.execute(
                text("INSERT INTO users (id, email, password_hash, status) VALUES (:i, :e, :h, :s)"),
                {"i": uid, "e": email, "h": hashed, "s": status},
            )
    await owner.dispose()


@pytest.fixture
async def clean(migrated, users):
    owner = create_async_engine(migrated)
    async with owner.begin() as conn:
        await conn.execute(text("DELETE FROM user_sessions"))
        await conn.execute(text("DELETE FROM login_throttle"))
    await owner.dispose()


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
async def app(migrated, clean, clock):
    application = create_app(Settings(environment="test", database_url=as_role(migrated, APP_ROLE)))
    application.state.clock = clock
    yield application
    await application.state.engine.dispose()


def client(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://nexora.test")


async def csrf(c: httpx.AsyncClient) -> dict[str, str]:
    if CSRF not in c.cookies:
        (await c.get("/v1/auth/csrf")).raise_for_status()
    return {"X-CSRF-Token": c.cookies[CSRF]}


async def login(c: httpx.AsyncClient, email="ada@example.sa", password=PASSWORD) -> httpx.Response:
    return await c.post("/v1/auth/login", json={"email": email, "password": password}, headers=await csrf(c))


# --- passwords ---------------------------------------------------------------------------------


def test_passwords_use_argon2id_and_verify():
    hashed = hash_password("s3cret-pass")
    assert hashed.startswith("$argon2id$")
    assert verify_password(hashed, "s3cret-pass")
    assert not verify_password(hashed, "wrong")
    assert not verify_password(None, "anything")


# --- login and sessions ------------------------------------------------------------------------


async def test_login_sets_hardened_cookies_and_me_works(app):
    async with client(app) as c:
        r = await login(c)
        assert r.status_code == 200
        assert r.json()["user"] == {"id": "usr_a", "email": "ada@example.sa", "name": ""}
        cookie = next(h for h in r.headers.get_list("set-cookie") if h.startswith(SESSION))
        low = cookie.lower()
        assert "httponly" in low
        assert "secure" in low
        assert "samesite=lax" in low
        assert "path=/" in low
        me = await c.get("/v1/me")
        assert me.status_code == 200
        assert me.json()["user"]["id"] == "usr_a"
        assert me.json()["is_platform_owner"] is False


async def test_session_id_is_stored_hashed(app, migrated):
    async with client(app) as c:
        await login(c)
        raw = c.cookies[SESSION]
    assert len(raw) >= 43  # 256 bits, url-safe base64
    owner = create_async_engine(migrated)
    async with owner.connect() as conn:
        stored = (await conn.execute(text("SELECT id_hash FROM user_sessions"))).scalars().all()
    await owner.dispose()
    assert stored == [hashlib.sha256(raw.encode()).hexdigest()]


async def test_case_insensitive_email(app):
    async with client(app) as c:
        assert (await login(c, email="ADA@Example.SA")).status_code == 200


@pytest.mark.parametrize(
    ("email", "password"),
    [("ada@example.sa", "wrong"), ("nobody@example.sa", PASSWORD), ("dis@example.sa", PASSWORD)],
)
async def test_failed_login_is_generic(app, email, password):
    async with client(app) as c:
        r = await login(c, email=email, password=password)
        assert r.status_code == 401
        assert r.json() == {"error": "invalid_credentials"}
        assert SESSION not in c.cookies


async def test_me_without_session_is_401(app):
    async with client(app) as c:
        assert (await c.get("/v1/me")).status_code == 401


async def test_logout_revokes_the_session(app):
    async with client(app) as c:
        await login(c)
        stolen = c.cookies[SESSION]
        assert (await c.post("/v1/auth/logout", headers=await csrf(c))).status_code == 204
    async with client(app) as other:
        other.cookies.set(SESSION, stolen, domain="nexora.test")
        assert (await other.get("/v1/me")).status_code == 401


async def test_logout_everywhere_revokes_all_sessions(app):
    async with client(app) as laptop, client(app) as phone:
        await login(laptop)
        await login(phone)
        assert (await phone.get("/v1/me")).status_code == 200
        assert (await laptop.post("/v1/auth/logout-all", headers=await csrf(laptop))).status_code == 204
        assert (await phone.get("/v1/me")).status_code == 401
        assert (await laptop.get("/v1/me")).status_code == 401


async def test_idle_timeout_is_12_hours(app, clock):
    async with client(app) as c:
        await login(c)
        clock.advance(hours=11)
        assert (await c.get("/v1/me")).status_code == 200  # activity renews the idle window
        clock.advance(hours=11)
        assert (await c.get("/v1/me")).status_code == 200
        clock.advance(hours=12, seconds=1)
        assert (await c.get("/v1/me")).status_code == 401


async def test_absolute_lifetime_is_7_days(app, clock):
    async with client(app) as c:
        await login(c)
        for _ in range(16):  # active every 10 h, never idle
            clock.advance(hours=10)
            last = await c.get("/v1/me")
        assert clock.now - datetime(2026, 11, 14, 9, 0, tzinfo=UTC) > timedelta(days=6)
        assert last.status_code == 200
        clock.advance(hours=10)
        assert (await c.get("/v1/me")).status_code == 401


# --- CSRF --------------------------------------------------------------------------------------


async def test_unsafe_requests_need_matching_csrf_token(app):
    async with client(app) as c:
        await csrf(c)
        body = {"email": "ada@example.sa", "password": PASSWORD}
        assert (await c.post("/v1/auth/login", json=body)).status_code == 403
        bad = await c.post("/v1/auth/login", json=body, headers={"X-CSRF-Token": "forged"})
        assert bad.status_code == 403
        assert bad.json() == {"error": "csrf_failed"}
        await login(c)
        assert (await c.post("/v1/auth/logout")).status_code == 403
        assert (await c.get("/v1/me")).status_code == 200  # the logout above did not happen


async def test_login_rotates_the_csrf_token(app):
    async with client(app) as c:
        before = (await csrf(c))["X-CSRF-Token"]
        await login(c)
        assert c.cookies[CSRF] != before


# --- lockout -----------------------------------------------------------------------------------


async def test_ten_failures_in_a_minute_lock_the_email_for_15_minutes(app, clock):
    async with client(app) as c:
        for _ in range(10):
            assert (await login(c, password="wrong")).status_code == 401
            clock.advance(seconds=5)
        locked = await login(c)  # even the right password is refused while locked
        assert locked.status_code == 429
        assert locked.json()["error"] == "locked"
        assert 0 < int(locked.headers["retry-after"]) <= 15 * 60
        clock.advance(minutes=14)
        assert (await login(c)).status_code == 429
        clock.advance(minutes=1, seconds=1)
        assert (await login(c)).status_code == 200


async def test_failures_spread_over_more_than_a_minute_do_not_lock(app, clock):
    async with client(app) as c:
        for _ in range(15):
            await login(c, password="wrong")
            clock.advance(seconds=7)  # never 10 within one minute window
        assert (await login(c)).status_code == 200


async def test_success_resets_the_failure_count(app, clock):
    async with client(app) as c:
        for _ in range(9):
            await login(c, password="wrong")
        assert (await login(c)).status_code == 200
        for _ in range(9):
            await login(c, password="wrong")
        assert (await login(c)).status_code == 200


async def test_lockout_applies_to_unknown_emails_too(app):
    async with client(app) as c:
        for _ in range(10):
            await login(c, email="ghost@example.sa", password="x")
        assert (await login(c, email="ghost@example.sa", password="x")).status_code == 429


async def test_lock_is_per_email(app):
    async with client(app) as c:
        for _ in range(10):
            await login(c, email="ghost@example.sa", password="x")
        assert (await login(c)).status_code == 200


# --- logging -----------------------------------------------------------------------------------


async def test_passwords_never_reach_the_logs(app, capsys):
    async with client(app) as c:
        await login(c, password="leaky-password-123")
        await login(c)
    out = capsys.readouterr()
    assert "leaky-password-123" not in out.out + out.err
    assert PASSWORD not in out.out + out.err


async def test_login_replaces_an_existing_session(app):
    async with client(app) as c:
        await login(c)
        first = c.cookies[SESSION]
        await login(c)
        assert c.cookies[SESSION] != first
    async with client(app) as other:
        other.cookies.set(SESSION, first, domain="nexora.test")
        assert (await other.get("/v1/me")).status_code == 401
