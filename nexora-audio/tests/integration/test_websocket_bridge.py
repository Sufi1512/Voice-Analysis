"""End-to-end over real WebSockets: client -> bridge -> fake agent -> client."""

import asyncio
import json

import numpy as np
import pytest

websockets = pytest.importorskip("websockets")

from nexora_audio import AudioFormat  # noqa: E402
from nexora_audio.integrations.websocket_bridge import BridgeConfig, handle_client  # noqa: E402
from nexora_audio.streaming.codecs import encode  # noqa: E402
from tests.audio_fixtures import mix, speech, white  # noqa: E402


def test_bridge_end_to_end() -> None:
    fmt = AudioFormat("pcm16", 16000)
    z = np.zeros(16000, np.float32)
    sig = np.concatenate([z, speech(16000), z])
    data = encode(mix(sig, white(len(sig)), 10)[None, :] * 0.8, fmt)

    received_audio = bytearray()
    received_events: list[dict] = []
    client_messages: list = []

    agent_done = asyncio.Event()

    async def fake_agent(ws: object) -> None:
        try:
            await _agent_loop(ws)
        finally:
            agent_done.set()

    async def _agent_loop(ws: object) -> None:
        async for msg in ws:  # type: ignore[attr-defined]
            if isinstance(msg, bytes):
                received_audio.extend(msg)
            else:
                ev = json.loads(msg)
                received_events.append(ev)
                if ev["type"] == "end_of_turn" and ev.get("reply_sent") is None:
                    await ws.send(b"\x00\x00" * 1600)  # type: ignore[attr-defined]  # 100 ms "TTS"
                    await ws.send(json.dumps({"type": "agent_reply"}))  # type: ignore[attr-defined]

    async def main() -> None:
        agent_srv = await websockets.serve(fake_agent, "127.0.0.1", 0)
        agent_port = agent_srv.sockets[0].getsockname()[1]
        cfg = BridgeConfig(agent_url=f"ws://127.0.0.1:{agent_port}", input_format=fmt)
        bridge_srv = await websockets.serve(lambda ws: handle_client(ws, cfg), "127.0.0.1", 0)
        bridge_port = bridge_srv.sockets[0].getsockname()[1]

        async with websockets.connect(f"ws://127.0.0.1:{bridge_port}") as client:

            async def reader() -> None:
                async for msg in client:
                    client_messages.append(msg)

            rt = asyncio.create_task(reader())
            step = fmt.bytes_for_ms(20)
            for i in range(0, len(data), step):
                await client.send(data[i : i + step])
                await asyncio.sleep(0.005)  # 4x real time, like a live caller (sped up)
            await client.send(json.dumps({"type": "client_hello"}))
            await asyncio.sleep(1.0)
            await client.close()
            await asyncio.wait_for(rt, 30)
        # the bridge processes the backlog, flushes, then closes the agent connection
        await asyncio.wait_for(agent_done.wait(), 60)
        bridge_srv.close()
        agent_srv.close()
        await bridge_srv.wait_closed()
        await agent_srv.wait_closed()

    asyncio.run(main())

    assert len(received_audio) >= len(data) * 0.95  # cleaned audio reached the agent
    types = [e["type"] for e in received_events]
    assert "speech_start" in types and "end_of_turn" in types
    assert {"type": "client_hello"} in received_events  # client JSON forwarded
    assert any(isinstance(m, bytes) for m in client_messages)  # agent audio reached client
    assert any(isinstance(m, str) and "agent_reply" in m for m in client_messages)
