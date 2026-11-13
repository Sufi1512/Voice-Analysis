"""Reference WebSocket bridge: client <-> nexora-audio <-> agent platform.

Needs ``pip install 'nexora-audio[server]'`` (websockets).

Protocol (adapt :class:`BridgeHooks` to your platform):

client -> bridge
    binary  raw audio in ``input_format`` (e.g. PCM16 16 kHz mono, any chunk size)
    text    JSON; forwarded to the agent unchanged

bridge -> agent (``agent_url``)
    binary  cleaned audio in ``output_format``
    text    JSON events: {"type": "speech_start" | "speech_end" | "end_of_turn" |
            "interruption" | "backchannel", "time_ms": ..., ...}

agent -> bridge -> client
    binary  agent audio (TTS). While it flows, the session knows the agent is speaking,
            so it can report "interruption" / "backchannel"
    text    JSON; forwarded to the client unchanged. ``{"type": "agent_speaking",
            "value": bool}`` also sets the speaking state explicitly.

On "interruption" the bridge also sends ``{"type": "interruption"}`` to the client so
it can stop playback immediately, without waiting for the agent.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from nexora_audio.streaming.codecs import AudioFormat
from nexora_audio.streaming.session import StreamSession
from nexora_audio.streaming.turns import TurnConfig

log = logging.getLogger("nexora_audio.bridge")


@dataclass
class BridgeConfig:
    agent_url: str
    input_format: AudioFormat = field(default_factory=AudioFormat)
    output_format: AudioFormat | None = None
    turns: TurnConfig | None = field(default_factory=TurnConfig)
    session_settings: dict[str, Any] = field(default_factory=dict)
    agent_silence_ms: float = 300.0  # agent counts as silent after this long without audio
    stop_client_on_interruption: bool = True


@dataclass
class BridgeHooks:
    """Override to adapt to your agent platform's protocol."""

    connect_agent: Callable[[str], Awaitable[Any]] | None = None

    def agent_event(self, event: dict[str, Any]) -> str | None:
        """Message sent to the agent for a nexora event (None to skip)."""
        return json.dumps(event)


async def handle_client(client: Any, cfg: BridgeConfig, hooks: BridgeHooks | None = None) -> None:
    """Serve one client connection until either side closes."""
    import websockets

    hooks = hooks or BridgeHooks()
    session = StreamSession(
        input_format=cfg.input_format,
        output_format=cfg.output_format,
        turns=cfg.turns,
        **cfg.session_settings,
    )
    connect = hooks.connect_agent or websockets.connect
    last_agent_audio = 0.0

    async with session, await connect(cfg.agent_url) as agent:

        async def client_to_agent() -> None:
            try:
                await _pump_client()
            except websockets.ConnectionClosed:
                log.info("client disconnected abruptly; flushing")
            await _finish()

        async def _pump_client() -> None:
            async for msg in client:
                if isinstance(msg, bytes):
                    out = await session.aprocess(msg)
                    if out.audio:
                        await agent.send(out.audio)
                    for ev in out.events:
                        payload = hooks.agent_event(ev.to_dict())
                        if payload is not None:
                            await agent.send(payload)
                        if ev.type == "interruption" and cfg.stop_client_on_interruption:
                            await client.send(json.dumps({"type": "interruption"}))
                else:
                    await agent.send(msg)

        async def _finish() -> None:
            tail = session.flush()
            if tail.audio:
                await agent.send(tail.audio)
            for ev in tail.events:
                payload = hooks.agent_event(ev.to_dict())
                if payload is not None:
                    await agent.send(payload)
            await agent.close()

        async def agent_to_client() -> None:
            nonlocal last_agent_audio
            async for msg in agent:
                if isinstance(msg, bytes):
                    last_agent_audio = time.monotonic()
                    session.set_agent_speaking(True)
                else:
                    with contextlib.suppress(ValueError, TypeError):
                        data = json.loads(msg)
                        if isinstance(data, dict) and data.get("type") == "agent_speaking":
                            session.set_agent_speaking(bool(data.get("value")))
                with contextlib.suppress(websockets.ConnectionClosed):
                    await client.send(msg)

        async def agent_silence_watch() -> None:
            while True:
                await asyncio.sleep(0.05)
                quiet = (time.monotonic() - last_agent_audio) * 1000 > cfg.agent_silence_ms
                if last_agent_audio and quiet:
                    session.set_agent_speaking(False)

        tasks = [
            asyncio.create_task(client_to_agent()),
            asyncio.create_task(agent_to_client()),
            asyncio.create_task(agent_silence_watch()),
        ]
        try:
            done, _ = await asyncio.wait(tasks[:2], return_when=asyncio.FIRST_COMPLETED)
            for t in done:
                if t.exception() and not isinstance(t.exception(), websockets.ConnectionClosed):
                    log.error("bridge task failed", exc_info=t.exception())
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


async def serve(
    cfg: BridgeConfig, host: str = "0.0.0.0", port: int = 8765, hooks: BridgeHooks | None = None
) -> None:
    """Run the bridge server forever."""
    import websockets

    async with websockets.serve(lambda ws: handle_client(ws, cfg, hooks), host, port):
        log.info("nexora bridge on ws://%s:%d -> %s", host, port, cfg.agent_url)
        await asyncio.Future()
