"""WebSocket streaming: process mode, tokens, limits, quota, relay, metering, metrics."""

from __future__ import annotations

import asyncio
import json
import threading
from typing import Any

import pytest

from tests.conftest import bearer, chunks, drain, new_org, speech_pcm16

websockets = pytest.importorskip("websockets")


def run_process_session(client: Any, key: str, audio: bytes, query: str = "") -> tuple:
    with client.websocket_connect(f"/v1/stream?{query}", headers=bearer(key)) as ws:
        started = ws.receive_json()
        for c in chunks(audio):
            ws.send_bytes(c)
        ws.send_text(json.dumps({"type": "end"}))
        msgs, out, code = drain(ws)
    return started, msgs, out, code


def test_process_mode_end_to_end_with_metering(client: Any) -> None:
    _, key = new_org(client)
    audio = speech_pcm16(pad_s=0.5)
    started, msgs, out, code = run_process_session(client, key, audio)

    assert started["type"] == "session.started" and started["mode"] == "process"
    assert started["backends"][0] in ("deepfilternet3", "rnnoise")
    assert started["input_format"] == {"encoding": "pcm16", "sample_rate": 16000, "channels": 1}
    assert code == 1000
    assert len(out) >= len(audio)  # cleaned audio for the whole stream, incl. flushed tail
    types = [m["type"] for m in msgs]
    assert "speech_start" in types and "end_of_turn" in types
    ended = msgs[-1]
    assert ended["type"] == "session.ended"
    duration = len(audio) / 2 / 16000
    assert ended["audio_seconds"] == pytest.approx(duration, abs=0.03)

    sessions = client.get("/v1/sessions", headers=bearer(key)).json()
    assert sessions[0]["status"] == "ended"
    assert sessions[0]["audio_seconds"] == pytest.approx(duration, abs=0.03)
    assert sessions[0]["event_counts"]["end_of_turn"] >= 1
    usage = client.get("/v1/usage", headers=bearer(key)).json()
    assert usage["audio_minutes"] == pytest.approx(duration / 60, abs=0.001)
    assert usage["sessions"] == 1 and usage["days"]

    metrics = client.get("/metrics").text
    assert 'nexora_sessions_total{mode="process",outcome="ok"} 1.0' in metrics
    assert "nexora_audio_seconds_total" in metrics


def test_telephony_format_and_profile(client: Any) -> None:
    _, key = new_org(client)
    client.post(
        "/v1/profiles",
        json={
            "name": "phone",
            "audio_settings": {"noise_backend": "rnnoise"},
            "turn_settings": None,
        },
        headers=bearer(key),
    )
    import numpy as np

    mulaw = bytes(np.full(8000, 0xFF, np.uint8))  # 1 s of mu-law silence
    with client.websocket_connect(
        "/v1/stream?encoding=mulaw&sample_rate=8000&profile=phone", headers=bearer(key)
    ) as ws:
        started = ws.receive_json()
        for i in range(0, len(mulaw), 160):
            ws.send_bytes(mulaw[i : i + 160])
        ws.send_text(json.dumps({"type": "end"}))
        msgs, out, code = drain(ws)
    assert started["backends"] == ["rnnoise", "voice-enhancer"]  # no VAD: turns disabled
    assert started["input_format"]["encoding"] == "mulaw" and code == 1000
    assert len(out) >= len(mulaw) and not [m for m in msgs if m["type"] == "speech_start"]


def test_session_token_auth(client: Any) -> None:
    _, key = new_org(client)
    tok = client.post("/v1/session-tokens", json={}, headers=bearer(key)).json()["token"]
    with client.websocket_connect(f"/v1/stream?token={tok}") as ws:  # no API key on the client
        assert ws.receive_json()["type"] == "session.started"
        ws.send_text(json.dumps({"type": "ping"}))
        assert ws.receive_json()["type"] == "pong"
        ws.send_text(json.dumps({"type": "end"}))
        _, _, code = drain(ws)
    assert code == 1000
    relay_tok = client.post(
        "/v1/session-tokens", json={"mode": "relay", "relay_target": "ws://x"}, headers=bearer(key)
    )
    assert relay_tok.status_code == 422  # x not allowlisted


@pytest.mark.parametrize(
    "path,headers,code",
    [
        ("/v1/stream", {}, 4001),
        ("/v1/stream?token=not.a.token", {}, 4001),
        ("/v1/stream?encoding=mp3", None, 4400),
        ("/v1/stream?profile=missing", None, 4004),
    ],
)
def test_rejections(client: Any, path: str, headers: dict | None, code: int) -> None:
    _, key = new_org(client)
    with client.websocket_connect(path, headers=bearer(key) if headers is None else headers) as ws:
        msgs, _, close = drain(ws)
    assert msgs[0]["type"] == "error" and msgs[0]["code"] == code and close == code


def test_stream_scope_required(client: Any) -> None:
    _, key = new_org(client)
    usage_key = client.post(
        "/v1/keys", json={"scopes": ["usage:read"]}, headers=bearer(key)
    ).json()["api_key"]
    with client.websocket_connect("/v1/stream", headers=bearer(usage_key)) as ws:
        _msgs, _, close = drain(ws)
    assert close == 4003


def test_org_concurrency_limit(client: Any) -> None:
    _, key = new_org(client, max_concurrent_sessions=1)
    with client.websocket_connect("/v1/stream", headers=bearer(key)) as first:
        assert first.receive_json()["type"] == "session.started"
        with client.websocket_connect("/v1/stream", headers=bearer(key)) as second:
            msgs, _, close = drain(second)
        assert close == 4429 and "limit" in msgs[0]["message"]
        first.send_text(json.dumps({"type": "end"}))
        drain(first)
    with client.websocket_connect("/v1/stream", headers=bearer(key)) as again:  # slot released
        assert again.receive_json()["type"] == "session.started"
        again.send_text(json.dumps({"type": "end"}))
        drain(again)


def test_server_capacity_limit(make_client: Any) -> None:
    client = make_client(max_sessions=1)
    _, key_a = new_org(client)
    _, key_b = new_org(client)
    with client.websocket_connect("/v1/stream", headers=bearer(key_a)) as ws:
        ws.receive_json()
        with client.websocket_connect("/v1/stream", headers=bearer(key_b)) as other:
            _, _, close = drain(other)
        assert close == 1013  # try another instance
        ws.send_text(json.dumps({"type": "end"}))
        drain(ws)
    assert 'nexora_rejections_total{reason="capacity"} 1.0' in client.get("/metrics").text


def test_quota(client: Any) -> None:
    _, key = new_org(client, monthly_minutes_quota=0)
    with client.websocket_connect("/v1/stream", headers=bearer(key)) as ws:
        msgs, _, close = drain(ws)
    assert close == 4402 and "quota" in msgs[0]["message"]


def test_message_size_and_idle_timeout(make_client: Any) -> None:
    client = make_client(max_message_bytes=2048, idle_timeout_s=0.5)
    _, key = new_org(client)
    with client.websocket_connect("/v1/stream", headers=bearer(key)) as ws:
        ws.receive_json()
        ws.send_bytes(b"\x00" * 4096)
        msgs, _, close = drain(ws)
    assert close == 1009 and msgs[-1]["reason"] == "message too big"
    with client.websocket_connect("/v1/stream", headers=bearer(key)) as ws:
        ws.receive_json()
        msgs, _, close = drain(ws)  # send nothing
    assert close == 4408


def test_session_pool_reuses_warm_sessions(client: Any) -> None:
    _, key = new_org(client)
    audio = speech_pcm16(pad_s=0.2, seconds=1.0)
    first = run_process_session(client, key, audio)[2]
    import time

    deadline = time.time() + 10
    while client.app.state.manager.idle_sessions() == 0 and time.time() < deadline:
        time.sleep(0.05)  # released session is reset in the background
    assert client.app.state.manager.idle_sessions() >= 1
    second = run_process_session(client, key, audio)[2]
    assert first == second  # a reused session behaves exactly like a fresh one


class FakeAgent:
    """A customer's agent platform: records what it gets, replies with 'TTS' audio."""

    def __init__(self) -> None:
        self.audio = bytearray()
        self.events: list[dict[str, Any]] = []
        self.port = 0
        self._ready = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop: asyncio.Future[None] | None = None
        self._thread = threading.Thread(target=self._run, daemon=True)

    def __enter__(self) -> FakeAgent:
        self._thread.start()
        self._ready.wait(10)
        return self

    def __exit__(self, *exc: object) -> None:
        if self._loop and self._stop:
            self._loop.call_soon_threadsafe(self._stop.set_result, None)
        self._thread.join(10)

    def _run(self) -> None:
        asyncio.run(self._main())

    async def _main(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._stop = self._loop.create_future()

        async def handler(ws: Any) -> None:
            async for msg in ws:
                if isinstance(msg, bytes):
                    self.audio.extend(msg)
                else:
                    ev = json.loads(msg)
                    self.events.append(ev)
                    if ev["type"] == "end_of_turn":
                        await ws.send(b"\x01\x00" * 3200)  # 200 ms of agent audio
                        await ws.send(json.dumps({"type": "agent_reply", "text": "hello"}))

        async with websockets.serve(handler, "127.0.0.1", 0) as srv:
            self.port = srv.sockets[0].getsockname()[1]
            self._ready.set()
            await self._stop


def test_relay_mode(client: Any) -> None:
    _, key = new_org(client, relay_allowlist=["127.0.0.1"])
    audio = speech_pcm16(pad_s=0.5)
    with FakeAgent() as agent:
        target = f"ws://127.0.0.1:{agent.port}/agent"
        with client.websocket_connect(f"/v1/relay?target={target}", headers=bearer(key)) as ws:
            started = ws.receive_json()
            for c in chunks(audio):
                ws.send_bytes(c)
            ws.send_text(json.dumps({"type": "custom", "x": 1}))  # forwarded to the agent
            import time

            time.sleep(1.0)  # let the agent reply
            ws.send_text(json.dumps({"type": "end"}))
            msgs, from_agent, code = drain(ws)
    assert started["mode"] == "relay" and code == 1000
    assert len(agent.audio) >= len(audio) * 0.95  # cleaned audio reached the agent
    types = [e["type"] for e in agent.events]
    assert "speech_start" in types and "end_of_turn" in types
    assert {"type": "custom", "x": 1} in agent.events
    assert len(from_agent) > 0  # agent audio reached the caller
    assert any(m.get("type") == "agent_reply" for m in msgs)


def test_relay_target_must_be_allowlisted(client: Any) -> None:
    _, key = new_org(client, relay_allowlist=["agent.example.com"])
    with client.websocket_connect("/v1/relay?target=ws://127.0.0.1:1/x", headers=bearer(key)) as ws:
        msgs, _, close = drain(ws)
    assert close == 4003 and "allowlist" in msgs[0]["message"]


def test_relay_unreachable_agent(client: Any) -> None:
    _, key = new_org(client, relay_allowlist=["127.0.0.1"])
    with client.websocket_connect("/v1/relay?target=ws://127.0.0.1:1/x", headers=bearer(key)) as ws:
        ws.receive_json()
        _msgs, _, close = drain(ws)
    assert close == 4502
