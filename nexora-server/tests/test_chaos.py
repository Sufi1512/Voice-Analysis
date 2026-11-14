"""E10 chaos tests: things fail mid-call. The server must free the slot, record the
session, and keep serving the next caller."""

from __future__ import annotations

import json
import os
import time
from typing import Any

import numpy as np
import pytest

from nexora_server.db import SessionRecord
from tests.conftest import bearer, chunks, drain, new_org, speech_pcm16


def wait_idle(client: Any, timeout: float = 5.0) -> None:
    mgr = client.app.state.manager
    deadline = time.time() + timeout
    while mgr.active and time.time() < deadline:
        time.sleep(0.02)
    assert mgr.active == 0, "a session slot leaked"


def still_serves(client: Any, key: str) -> None:
    with client.websocket_connect("/v1/stream", headers=bearer(key)) as ws:
        assert ws.receive_json()["type"] == "session.started"
        for c in chunks(speech_pcm16(pad_s=0.1))[:20]:
            ws.send_bytes(c)
        ws.send_text(json.dumps({"type": "end"}))
        _, out, code = drain(ws)
    assert code == 1000 and out


def records(client: Any) -> list[SessionRecord]:
    from sqlalchemy import select

    with client.app.state.db.session() as s:
        return list(s.scalars(select(SessionRecord)))


def test_client_vanishes_mid_call(client: Any) -> None:
    _, key = new_org(client)
    with client.websocket_connect("/v1/stream", headers=bearer(key)) as ws:
        ws.receive_json()
        for c in chunks(speech_pcm16())[:30]:
            ws.send_bytes(c)
        # leave without "end": the socket just closes
    wait_idle(client)
    deadline = time.time() + 5  # the record is written just after the slot is freed
    while records(client)[0].status == "active" and time.time() < deadline:
        time.sleep(0.02)
    (rec,) = records(client)
    # the in-process test client drops queued audio on disconnect; the real-server test
    # below checks that audio received before a drop is recorded
    assert rec.status == "ended" and rec.ended_at is not None
    still_serves(client, key)


def test_database_down_when_the_call_ends(client: Any, monkeypatch: Any) -> None:
    from nexora_server.streaming import ws as ws_mod

    _, key = new_org(client)

    def broken(*a: Any, **k: Any) -> None:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(ws_mod, "_finish_record", broken)
    with client.websocket_connect("/v1/stream", headers=bearer(key)) as ws:
        ws.receive_json()
        for c in chunks(speech_pcm16())[:20]:
            ws.send_bytes(c)
        ws.send_text(json.dumps({"type": "end"}))
        msgs, _, _ = drain(ws)
    assert any(m.get("type") == "session.ended" for m in msgs)  # the caller still gets it
    wait_idle(client)
    monkeypatch.undo()
    still_serves(client, key)


def test_audio_engine_crashes_mid_call(client: Any, monkeypatch: Any) -> None:
    from nexora_audio import StreamSession

    _, key = new_org(client)
    real = StreamSession.process
    calls = {"n": 0}

    def flaky(self: Any, data: bytes) -> Any:
        calls["n"] += 1
        if calls["n"] == 10:
            raise RuntimeError("native library fault")
        return real(self, data)

    monkeypatch.setattr(StreamSession, "process", flaky)
    with client.websocket_connect("/v1/stream", headers=bearer(key)) as ws:
        ws.receive_json()
        for c in chunks(speech_pcm16())[:30]:
            try:
                ws.send_bytes(c)
            except Exception:
                break
        msgs, _, code = drain(ws)
    assert code == 1011 and any(m.get("code") == 1011 for m in msgs)
    wait_idle(client)
    assert records(client)[0].status == "failed"
    monkeypatch.undo()
    still_serves(client, key)  # the broken session was not put back in the warm pool


def test_garbage_input_is_refused_not_fatal(client: Any) -> None:
    _, key = new_org(client)
    rng = np.random.default_rng(7)
    with client.websocket_connect("/v1/stream", headers=bearer(key)) as ws:
        ws.receive_json()
        ws.send_bytes(rng.integers(0, 256, 641, dtype=np.uint8).tobytes())  # odd length
        for bad in [
            "{not json",
            "[1, 2, 3]",
            '{"type": 42}',
            '{"type": "agent_audio"}',
            json.dumps({"type": "transcript", "text": "x" * 10_000}),
            json.dumps({"type": "unknown_kind", "x": 1}),
        ]:
            ws.send_text(bad)
        ws.send_bytes(b"")
        ws.send_text(json.dumps({"type": "end"}))
        msgs, _, code = drain(ws)
    assert code in (1000, 4400)
    assert any(m.get("type") == "error" for m in msgs)
    wait_idle(client)
    still_serves(client, key)


@pytest.mark.skipif(not os.environ.get("NEXORA_CHAOS_RELAY", "1"), reason="disabled")
def test_relay_agent_dies_mid_call(client: Any) -> None:
    import asyncio
    import threading

    websockets = pytest.importorskip("websockets")
    port_box: dict[str, int] = {}
    ready = threading.Event()

    async def agent_main() -> None:
        async def handler(ws: Any) -> None:
            n = 0
            async for _ in ws:
                n += 1
                if n == 15:  # the agent crashes mid-call
                    await ws.close(code=1011, reason="agent crashed")
                    return

        async with websockets.serve(handler, "127.0.0.1", 0) as srv:
            port_box["p"] = srv.sockets[0].getsockname()[1]
            ready.set()
            await asyncio.sleep(10)

    threading.Thread(target=lambda: asyncio.run(agent_main()), daemon=True).start()
    ready.wait(5)
    _, key = new_org(client, relay_allowlist=["127.0.0.1"])
    target = f"ws://127.0.0.1:{port_box['p']}/agent"
    with client.websocket_connect(f"/v1/relay?target={target}", headers=bearer(key)) as ws:
        assert ws.receive_json()["type"] == "session.started"
        for c in chunks(speech_pcm16())[:60]:
            try:
                ws.send_bytes(c)
            except Exception:
                break
            time.sleep(0.005)
        msgs, _, _code = drain(ws)
    ended = [m for m in msgs if m.get("type") == "session.ended"]
    assert ended and "agent" in str(ended[0].get("reason"))
    wait_idle(client)
    still_serves(client, key)


def test_tcp_connection_dropped_on_a_real_server(tmp_path: Any) -> None:
    """The same as a caller losing signal: the TCP connection just dies (no close frame)."""
    import asyncio
    import socket
    import threading

    import httpx
    import uvicorn

    from nexora_server.app import create_app
    from tests.conftest import ADMIN, make_settings

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    app = create_app(make_settings(tmp_path), prewarm=False)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_config=None))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            if httpx.get(f"{base}/readyz").status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.1)
    key = httpx.post(
        f"{base}/v1/orgs", json={"name": "Drop"}, headers={"Authorization": f"Bearer {ADMIN}"}
    ).json()["api_key"]

    async def call_then_vanish() -> None:
        import websockets

        ws = await websockets.connect(
            f"ws://127.0.0.1:{port}/v1/stream",
            additional_headers={"Authorization": f"Bearer {key}"},
        )
        await ws.recv()
        for c in chunks(speech_pcm16())[:40]:
            await ws.send(c)
        await asyncio.sleep(0.3)
        ws.transport.abort()  # no close frame, like a dropped mobile connection

    try:
        asyncio.run(call_then_vanish())
        from sqlalchemy import select

        deadline = time.time() + 10
        rec = None
        while time.time() < deadline:
            with app.state.db.session() as s:
                rec = s.scalar(select(SessionRecord))
            if rec is not None and rec.status != "active":
                break
            time.sleep(0.05)
        assert rec is not None and rec.status in ("ended", "failed"), rec and rec.status
        assert rec.audio_seconds > 0.5  # the audio received before the drop is recorded
        assert app.state.manager.active == 0
    finally:
        server.should_exit = True
        t.join(10)
