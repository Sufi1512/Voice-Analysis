"""Real server (uvicorn on a port) + the nexora_client SDK, as a customer would use them."""

from __future__ import annotations

import asyncio
import socket
import threading
import time
from pathlib import Path
from typing import Any

import httpx
import pytest

nexora_client = pytest.importorskip("nexora_client")
uvicorn = pytest.importorskip("uvicorn")

from nexora_server.app import create_app  # noqa: E402
from tests.conftest import ADMIN, chunks, make_settings, speech_pcm16  # noqa: E402


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


@pytest.fixture
def live_server(tmp_path: Path) -> Any:
    port = free_port()
    app = create_app(make_settings(tmp_path), prewarm=True)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_config=None))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            if httpx.get(f"{base}/readyz").status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    else:
        pytest.fail("server did not become ready")
    yield base
    server.should_exit = True
    t.join(15)


def test_customer_flow(live_server: str) -> None:
    base = live_server
    r = httpx.post(
        f"{base}/v1/orgs", json={"name": "Customer"}, headers={"Authorization": f"Bearer {ADMIN}"}
    )
    api_key = r.json()["api_key"]
    audio = speech_pcm16(pad_s=0.5)

    async def main() -> tuple[list[str], int, dict[str, Any] | None, dict[str, Any], float]:
        async with nexora_client.NexoraClient(base, api_key) as nx:
            events: list[str] = []
            received = 0
            t_first_byte = 0.0
            async with nx.stream(encoding="pcm16", sample_rate=16000) as stream:
                assert stream.session_id.startswith("ses_")

                async def reader() -> None:
                    nonlocal received, t_first_byte
                    async for msg in stream:
                        if msg.audio:
                            if not received:
                                t_first_byte = time.perf_counter()
                            received += len(msg.audio)
                        elif msg.type in nexora_client.TURN_EVENTS:
                            events.append(msg.type)

                task = asyncio.create_task(reader())
                t_start = time.perf_counter()
                for c in chunks(audio):
                    await stream.send_audio(c)
                    await asyncio.sleep(0.004)  # ~5x real time
                await stream.request_end()
                await asyncio.wait_for(task, 30)
                summary = stream.summary
            usage = await nx.usage()
            token = await nx.create_session_token()
        return events, received, summary, {"usage": usage, "token": token}, t_first_byte - t_start

    events, received, summary, extra, first_byte_s = asyncio.run(main())
    assert received >= len(audio)
    assert "speech_start" in events and "end_of_turn" in events
    assert summary is not None and summary["audio_seconds"] == pytest.approx(
        len(audio) / 32000, abs=0.05
    )
    assert extra["usage"]["sessions"] == 1
    assert extra["token"]["token"]
    assert first_byte_s < 1.0  # warm pool: audio flows back immediately


def test_rejection_surfaces_as_exception(live_server: str) -> None:
    async def main() -> None:
        async with (
            nexora_client.NexoraClient(live_server, "nx_000000000000_bad") as nx,
            nx.stream(),
        ):
            pass

    with pytest.raises(nexora_client.NexoraError) as exc:
        asyncio.run(main())
    assert exc.value.code == 4001
