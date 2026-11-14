"""Call lifecycle fixes from the bug round (OPEN_ISSUES.md):

- I-030: running calls are checkpointed; calls whose server died are swept and billed.
- I-026: the live number of calls per organization, on every server.
- I-029: usage pages count a call on the day it ended, like billing.
- I-035: new connections are rate limited per client IP before the handshake.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from nexora_server.db import Organization, SessionRecord
from nexora_server.limits import ConnectRateLimiter
from nexora_server.services import LOST_REASON, sweep_stale_sessions
from tests.conftest import admin, bearer, chunks, drain, new_org, speech_pcm16


def _record(client: Any, **fields: Any) -> str:
    with client.app.state.db.session() as s:
        rec = SessionRecord(mode="process", **fields)
        s.add(rec)
        s.flush()
        return rec.id


def _get(client: Any, rid: str) -> SessionRecord:
    with client.app.state.db.session() as s:
        rec = s.get(SessionRecord, rid)
        assert rec is not None
        return rec


# ---- I-030: checkpoints and the lost-call sweeper ----------------------------------------


def test_a_running_call_saves_its_audio_and_heartbeat(make_client: Any) -> None:
    client = make_client(checkpoint_interval_s=1.0, stale_session_after_s=2.0)
    _, key = new_org(client)
    with client.websocket_connect("/v1/stream", headers=bearer(key)) as ws:
        rid = ws.receive_json()["session_id"]
        first = _get(client, rid).heartbeat_at
        for c in chunks(speech_pcm16(pad_s=0.1))[:100]:  # 2 s of audio
            ws.send_bytes(c)
        time.sleep(1.6)
        mid = _get(client, rid)
        assert mid.status == "active"
        assert mid.audio_seconds > 0.5, "audio not checkpointed while the call runs"
        assert mid.heartbeat_at is not None and first is not None and mid.heartbeat_at > first
        ws.send_text(json.dumps({"type": "end"}))
        drain(ws)
    done = _get(client, rid)
    assert done.status == "ended" and done.heartbeat_at == done.ended_at


def test_sweeper_closes_lost_calls_at_their_last_heartbeat(client: Any) -> None:
    org_id, _ = new_org(client)
    now = datetime.now(UTC)
    lost = _record(
        client,
        org_id=org_id,
        started_at=now - timedelta(minutes=30),
        heartbeat_at=now - timedelta(minutes=10),
        audio_seconds=1200.0,
    )
    never_beat = _record(client, org_id=org_id, started_at=now - timedelta(minutes=5))
    alive = _record(client, org_id=org_id, started_at=now - timedelta(minutes=30), heartbeat_at=now)
    with client.app.state.db.session() as s:
        assert sweep_stale_sessions(s, 120.0, now) == 2
    with client.app.state.db.session() as s:  # a second sweep (another server) is a no-op
        assert sweep_stale_sessions(s, 120.0, now) == 0
    rec = _get(client, lost)
    assert rec.status == "failed" and rec.close_reason == LOST_REASON
    assert rec.ended_at is not None and abs(
        rec.ended_at.replace(tzinfo=UTC) - (now - timedelta(minutes=10))
    ) < timedelta(seconds=1)
    assert rec.audio_seconds == 1200.0  # billed up to the last checkpoint
    assert _get(client, never_beat).status == "failed"
    assert _get(client, alive).status == "active"


def test_the_server_sweeps_by_itself(make_client: Any) -> None:
    client = make_client(checkpoint_interval_s=0.2, stale_session_after_s=0.5)
    org_id, _ = new_org(client)
    old = datetime.now(UTC) - timedelta(minutes=5)
    rid = _record(client, org_id=org_id, started_at=old, heartbeat_at=old, audio_seconds=60.0)
    deadline = time.time() + 5
    while _get(client, rid).status == "active" and time.time() < deadline:
        time.sleep(0.05)
    assert _get(client, rid).status == "failed"
    assert client.app.state.metrics.swept._value.get() >= 1


def test_a_lost_call_is_billed_in_the_next_report(client: Any) -> None:
    """The sweeper back-dates the end into an hour that may already be reported; the next
    report carries it (reports are running totals), so nothing is lost or billed twice."""
    from nexora_server.billing import report_usage

    sent: list[int] = []

    class Meter:
        def send(self, *, customer: str, value: int, at: datetime, identifier: str) -> None:
            sent.append(value)

    org_id, _ = new_org(client)
    t0 = datetime(2026, 11, 1, 10, 0, tzinfo=UTC)
    with client.app.state.db.session() as s:
        org = s.get(Organization, org_id)
        assert org is not None
        org.stripe_customer_id, org.created_at = "cus_test", t0
    _record(
        client,
        org_id=org_id,
        status="ended",
        started_at=t0 + timedelta(minutes=5),
        ended_at=t0 + timedelta(minutes=10),
        audio_seconds=300.0,
    )
    lost = _record(
        client,
        org_id=org_id,
        started_at=t0 + timedelta(minutes=20),
        heartbeat_at=t0 + timedelta(minutes=50),
        audio_seconds=1800.0,
    )
    db = client.app.state.db
    report_usage(db, Meter(), now=t0 + timedelta(hours=1, minutes=10))  # 10:00-11:00 sent
    assert sent == [300]
    with db.session() as s:  # the server running the lost call died; the sweep runs now
        sweep_stale_sessions(s, 120.0, t0 + timedelta(hours=1, minutes=20))
    assert _get(client, lost).ended_at is not None
    report_usage(db, Meter(), now=t0 + timedelta(hours=2, minutes=10))  # 11:00-12:00
    assert sent == [300, 1800] and sum(sent) == 2100


def test_settings_refuse_a_sweep_faster_than_checkpoints(tmp_path: Any) -> None:
    from tests.conftest import make_settings

    with pytest.raises(ValueError, match="stale_session_after_s"):
        make_settings(tmp_path, checkpoint_interval_s=30.0, stale_session_after_s=40.0)


# ---- I-026: calls right now ---------------------------------------------------------------


def test_usage_shows_calls_running_now(client: Any) -> None:
    org_id, key = new_org(client)
    assert client.get("/v1/usage", headers=bearer(key)).json()["active_sessions"] == 0
    with client.websocket_connect("/v1/stream", headers=bearer(key)) as ws:
        ws.receive_json()
        # another server's call, seen through the database
        _record(client, org_id=org_id, heartbeat_at=datetime.now(UTC))
        assert client.get("/v1/usage", headers=bearer(key)).json()["active_sessions"] == 2
        ws.send_text(json.dumps({"type": "end"}))
        drain(ws)
    assert client.get("/v1/usage", headers=bearer(key)).json()["active_sessions"] == 1


# ---- I-029: usage by the day a call ended --------------------------------------------------


def test_a_call_across_midnight_counts_on_the_day_it_ended(client: Any) -> None:
    org_id, key = new_org(client)
    midnight = datetime(2026, 11, 2, tzinfo=UTC)
    _record(
        client,
        org_id=org_id,
        status="ended",
        started_at=midnight - timedelta(minutes=10),
        ended_at=midnight + timedelta(minutes=10),
        audio_seconds=1200.0,
    )
    _record(client, org_id=org_id, started_at=midnight - timedelta(minutes=1))  # running
    r = client.get(
        "/v1/usage",
        params={"start": "2026-11-01T00:00:00Z", "end": "2026-11-03T00:00:00Z"},
        headers=bearer(key),
    ).json()
    assert r["days"] == [{"date": "2026-11-02", "audio_minutes": 20.0, "sessions": 1}]
    assert r["audio_minutes"] == 20.0 and r["sessions"] == 1


# ---- I-035: connection rate limit per client IP --------------------------------------------


def test_token_bucket() -> None:
    lim = ConnectRateLimiter(rate_per_s=1.0, burst=3, max_clients=2)
    assert [lim.allow("a", now=0.0) for _ in range(4)] == [True, True, True, False]
    assert lim.retry_after_s("a") == 1
    assert lim.allow("a", now=1.0) and not lim.allow("a", now=1.0)
    assert lim.allow("b", now=1.0)  # other addresses are not affected
    lim.allow("c", now=1.0)  # three addresses, room for two: the oldest is forgotten
    assert "a" not in lim._buckets and len(lim._buckets) == 2
    assert all(ConnectRateLimiter(0, 1).allow("x") for _ in range(100))  # 0: off


def test_floods_from_one_address_get_429_before_the_handshake(make_client: Any) -> None:
    from starlette.testclient import WebSocketDenialResponse

    client = make_client(connect_rate_per_ip=0.001, connect_burst_per_ip=2)
    _, key = new_org(client)
    for _ in range(2):
        with client.websocket_connect("/v1/stream", headers=bearer(key)) as ws:
            ws.receive_json()
            ws.send_text(json.dumps({"type": "end"}))
            drain(ws)
    with (
        pytest.raises(WebSocketDenialResponse) as denied,
        client.websocket_connect("/v1/stream", headers=bearer(key)),
    ):
        pass
    assert denied.value.status_code == 429
    assert int(denied.value.headers["retry-after"]) >= 1
    assert client.app.state.metrics.rejections.labels("rate_limited")._value.get() == 1
    assert client.get("/healthz").status_code == 200  # the REST API is not limited
    assert client.get("/v1/orgs", headers=admin()).status_code == 200


def test_429_on_a_real_server_and_forwarded_client_ips(tmp_path: Any) -> None:
    """uvicorn sends the HTTP 429; behind a trusted proxy the limit is per real client."""
    import asyncio
    import socket
    import threading

    import uvicorn
    import websockets

    from nexora_server.app import create_app
    from tests.conftest import make_settings

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    app = create_app(
        make_settings(tmp_path, connect_rate_per_ip=0.001, connect_burst_per_ip=1),
        prewarm=False,
    )
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            log_config=None,
            proxy_headers=True,
            forwarded_allow_ips="127.0.0.1",
        )
    )
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    deadline = time.time() + 30
    while not server.started and time.time() < deadline:
        time.sleep(0.05)

    async def attempt(client_ip: str) -> int:
        try:
            async with websockets.connect(
                f"ws://127.0.0.1:{port}/v1/stream",
                additional_headers={"X-Forwarded-For": client_ip},
            ) as ws:
                await ws.recv()  # no key: refused after the handshake (4401)
                return 101
        except websockets.InvalidStatus as exc:
            return int(exc.response.status_code)
        except websockets.ConnectionClosed:
            return 101

    async def run() -> list[int]:
        return [
            await attempt("203.0.113.7"),
            await attempt("203.0.113.7"),
            await attempt("198.51.100.9"),  # a different caller behind the same proxy
        ]

    try:
        assert asyncio.run(run()) == [101, 429, 101]
    finally:
        server.should_exit = True
        t.join(10)
