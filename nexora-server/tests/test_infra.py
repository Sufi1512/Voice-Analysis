"""E6: cluster-wide organization limits (Redis leases), draining, migrations."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, inspect

from tests.conftest import bearer, chunks, drain, new_org, speech_pcm16

fakeredis = pytest.importorskip("fakeredis")

from nexora_server.limits import RedisOrgLimiter  # noqa: E402

# -- Redis leases -----------------------------------------------------------------------


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def test_limit_holds_across_instances() -> None:
    server = fakeredis.FakeServer()

    async def go() -> None:
        a = RedisOrgLimiter(fakeredis.aioredis.FakeRedis(server=server))
        b = RedisOrgLimiter(fakeredis.aioredis.FakeRedis(server=server))
        la = await a.acquire("org_1", 2)
        lb = await b.acquire("org_1", 2)
        assert la and lb
        assert await b.acquire("org_1", 2) is None  # 2 held across both instances
        assert await a.acquire("org_2", 2)  # other organizations are separate
        assert await a.cluster_count("org_1") == 2
        assert a.active_for("org_1") == 1 and b.active_for("org_1") == 1
        await a.release("org_1", la)
        assert await b.acquire("org_1", 2)  # the freed slot is usable elsewhere

    run(go())


def test_lease_of_a_crashed_instance_expires() -> None:
    async def go() -> None:
        server = fakeredis.FakeServer()
        dead = RedisOrgLimiter(fakeredis.aioredis.FakeRedis(server=server), ttl_s=0.3)
        live = RedisOrgLimiter(fakeredis.aioredis.FakeRedis(server=server), ttl_s=0.3)
        assert await dead.acquire("org_1", 1)  # never renewed or released
        assert await live.acquire("org_1", 1) is None
        await asyncio.sleep(0.45)
        assert await live.acquire("org_1", 1)

    run(go())


def test_renewal_keeps_the_lease() -> None:
    async def go() -> None:
        server = fakeredis.FakeServer()
        a = RedisOrgLimiter(fakeredis.aioredis.FakeRedis(server=server), ttl_s=0.3)
        lease = await a.acquire("org_1", 1)
        assert lease
        for _ in range(4):
            await asyncio.sleep(0.15)
            await a.renew("org_1", lease)
        assert await a.acquire("org_1", 1) is None  # still held after 0.6 s

    run(go())


class _BrokenRedis:
    def register_script(self, _: str) -> Any:
        async def call(**_: Any) -> Any:
            raise ConnectionError("redis down")

        return call

    async def zrem(self, *_: Any) -> Any:
        raise ConnectionError("redis down")


def test_redis_down_falls_back_to_local_count() -> None:
    errors: list[int] = []
    limiter = RedisOrgLimiter(_BrokenRedis(), on_error=lambda: errors.append(1))

    async def go() -> None:
        l1 = await limiter.acquire("org_1", 1)
        assert l1 is not None  # calls keep working
        assert await limiter.acquire("org_1", 1) is None  # limit is now per instance
        await limiter.release("org_1", l1)
        assert await limiter.acquire("org_1", 1) is not None

    run(go())
    assert errors


def test_org_limit_across_two_servers(make_client: Any) -> None:
    """Two server instances sharing one Redis: the organization's limit is cluster-wide."""
    server = fakeredis.FakeServer()
    a, b = make_client(), make_client()
    for c in (a, b):
        c.app.state.manager.limiter = RedisOrgLimiter(fakeredis.aioredis.FakeRedis(server=server))
    _, key = new_org(a, max_concurrent_sessions=1)  # both servers share one database file
    with a.websocket_connect("/v1/stream", headers=bearer(key)) as ws:
        assert ws.receive_json()["type"] == "session.started"
        with b.websocket_connect("/v1/stream", headers=bearer(key)) as ws2:
            err = ws2.receive_json()
        assert err["type"] == "error" and err["code"] == 4429
        ws.send_text(json.dumps({"type": "end"}))
        drain(ws)
    with b.websocket_connect("/v1/stream", headers=bearer(key)) as ws3:
        assert ws3.receive_json()["type"] == "session.started"
        ws3.send_text(json.dumps({"type": "end"}))
        drain(ws3)


# -- draining ---------------------------------------------------------------------------


def test_draining_refuses_new_sessions_and_keeps_open_ones(client: Any) -> None:
    _, key = new_org(client)
    audio = speech_pcm16(pad_s=0.2)
    with client.websocket_connect("/v1/stream", headers=bearer(key)) as ws:
        ws.receive_json()
        cs = chunks(audio)
        for c in cs[: len(cs) // 2]:
            ws.send_bytes(c)
        client.app.state.start_draining()
        r = client.get("/readyz")
        assert r.status_code == 503 and r.json()["draining"] is True
        with client.websocket_connect("/v1/stream", headers=bearer(key)) as ws2:
            err = ws2.receive_json()
        assert err["code"] == 1013 and "draining" in err["message"]
        for c in cs[len(cs) // 2 :]:  # the open call carries on
            ws.send_bytes(c)
        ws.send_text(json.dumps({"type": "end"}))
        msgs, out, code = drain(ws)
    assert code == 1000 and len(out) > 0
    ended = [m for m in msgs if m.get("type") == "session.ended"]
    assert ended and ended[0]["close_code"] == 1000
    metrics = client.get("/metrics").text
    assert "nexora_draining 1.0" in metrics and 'reason="draining"' in metrics


class _Mgr:
    def __init__(self, active: int) -> None:
        self.active = active


def test_wait_until_idle() -> None:
    from nexora_server.__main__ import wait_until_idle

    m = _Mgr(0)
    assert wait_until_idle(m, 1.0)
    m = _Mgr(1)
    t = time.monotonic()
    assert not wait_until_idle(m, 0.3, poll_s=0.05)
    assert 0.25 < time.monotonic() - t < 1.0


def test_draining_server_exits_only_when_idle() -> None:
    import threading

    import uvicorn

    from nexora_server.__main__ import _server_class

    class State:
        ready = True
        manager = _Mgr(1)
        drained = False

        def start_draining(self) -> None:
            self.drained = True

    class App:
        state = State()

    app = App()
    srv = _server_class()(uvicorn.Config(app), app, drain_timeout_s=5)
    srv.handle_exit(15, None)
    assert app.state.drained and not srv.should_exit  # still serving the open call
    app.state.manager.active = 0
    deadline = time.monotonic() + 3
    while not srv.should_exit and time.monotonic() < deadline:
        time.sleep(0.05)
    assert srv.should_exit
    assert not any(t.name == "drain" and t.is_alive() for t in threading.enumerate())


# -- migrations -------------------------------------------------------------------------


def _tables(url: str) -> set[str]:
    eng = create_engine(url)
    try:
        return set(inspect(eng).get_table_names())
    finally:
        eng.dispose()


def test_migrations_match_the_models(tmp_path: Path) -> None:
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from nexora_server.db import Base
    from nexora_server.migrate import downgrade, upgrade

    url = f"sqlite:///{tmp_path / 'm.db'}"
    upgrade(url)
    eng = create_engine(url)
    with eng.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    eng.dispose()
    assert diff == []
    downgrade(url, "base")
    assert _tables(url) == {"alembic_version"}
    upgrade(url)
    assert "organizations" in _tables(url)


def _version(url: str) -> str:
    from sqlalchemy import text

    eng = create_engine(url)
    with eng.connect() as conn:
        v = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    eng.dispose()
    return str(v)


def test_create_all_databases_are_stamped_not_recreated(tmp_path: Path) -> None:
    from nexora_server.db import Base, Database, SsoMember, UsageReport
    from nexora_server.migrate import upgrade

    current = f"sqlite:///{tmp_path / 'current.db'}"
    Database(current).create_all()
    upgrade(current)  # must not try to create the tables again
    assert _version(current) == "0002"

    e1 = f"sqlite:///{tmp_path / 'e1.db'}"  # an E1-era database: only the first tables
    eng = create_engine(e1)
    skip = {SsoMember.__table__.name, UsageReport.__table__.name}
    first = [t for t in Base.metadata.sorted_tables if t.name not in skip]
    Base.metadata.create_all(eng, tables=first)
    with eng.begin() as conn:
        from sqlalchemy import text

        conn.execute(text("ALTER TABLE organizations DROP COLUMN stripe_customer_id"))
    eng.dispose()
    upgrade(e1)
    assert _version(e1) == "0002" and {"usage_reports", "sso_members"} <= _tables(e1)


def test_migrations_on_postgres() -> None:
    """CI runs this against a real PostgreSQL (NEXORA_TEST_POSTGRES_URL)."""
    import os

    url = os.environ.get("NEXORA_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("NEXORA_TEST_POSTGRES_URL not set")
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from nexora_server.db import Base
    from nexora_server.migrate import downgrade, upgrade

    upgrade(url)
    eng = create_engine(url)
    with eng.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    eng.dispose()
    assert diff == []
    downgrade(url, "base")
    upgrade(url)
