"""C1: the Core service starts, reports health and readiness, and refuses unsafe settings."""

import httpx
import pytest
from pydantic import ValidationError

from nexora_core.app import create_app
from nexora_core.settings import Settings


def client_for(settings: Settings) -> httpx.AsyncClient:
    app = create_app(settings)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://core")


async def test_healthz_ok():
    async with client_for(
        Settings(environment="test", database_url="postgresql+asyncpg://x:x@127.0.0.1:1/x")
    ) as c:
        r = await c.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_readyz_503_when_database_down():
    async with client_for(
        Settings(environment="test", database_url="postgresql+asyncpg://x:x@127.0.0.1:1/x")
    ) as c:
        r = await c.get("/readyz")
    assert r.status_code == 503
    assert r.json()["checks"]["database"] == "down"


async def test_readyz_200_when_database_up(database_url):
    async with client_for(Settings(environment="test", database_url=database_url)) as c:
        r = await c.get("/readyz")
    assert r.status_code == 200
    assert r.json() == {"status": "ready", "checks": {"database": "up"}}


def test_production_requires_session_secret():
    with pytest.raises(ValidationError, match="session_secret"):
        Settings(environment="production", database_url="postgresql+asyncpg://x:x@db/x", session_secret="")


def test_production_rejects_short_session_secret():
    with pytest.raises(ValidationError, match="session_secret"):
        Settings(
            environment="production", database_url="postgresql+asyncpg://x:x@db/x", session_secret="short"
        )


def test_settings_read_from_environment(monkeypatch):
    monkeypatch.setenv("NEXORA_ENVIRONMENT", "test")
    monkeypatch.setenv("NEXORA_DATABASE_URL", "postgresql+asyncpg://a:b@h/d")
    s = Settings()
    assert s.database_url == "postgresql+asyncpg://a:b@h/d"
    assert s.self_signup is False  # enterprise first (P1 spec)
