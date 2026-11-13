"""Python client for Nexora Voice Cloud.

Server side (your backend, holds the API key)::

    from nexora_client import NexoraClient

    async with NexoraClient("https://voice.example.com", api_key="nx_...") as nx:
        async with nx.stream(encoding="pcm16", sample_rate=16000) as stream:
            await stream.send_audio(chunk)
            async for msg in stream:
                if msg.audio:          # cleaned audio
                    ...
                elif msg.event:        # {"type": "end_of_turn", ...}
                    ...

Browser / mobile (no API key on the device): your backend calls
``nx.create_session_token()`` and passes the token to the device, which connects to
``wss://voice.example.com/v1/stream?token=...``.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from types import TracebackType
from typing import Any
from urllib.parse import urlencode

import httpx
from typing_extensions import Self

__version__ = "0.1.0.dev0"
__all__ = ["Message", "NexoraClient", "NexoraError", "NexoraStream", "SessionClosed"]


class NexoraError(Exception):
    def __init__(self, message: str, code: int | None = None) -> None:
        super().__init__(f"{message} (code {code})" if code else message)
        self.code = code


class SessionClosed(NexoraError):
    """The server ended the session. ``summary`` holds the session.ended message, if any."""

    def __init__(self, code: int | None, reason: str, summary: dict[str, Any] | None) -> None:
        super().__init__(reason, code)
        self.summary = summary


@dataclass(frozen=True)
class Message:
    """One server message: cleaned audio, a turn event, or a control/agent message."""

    audio: bytes | None = None
    event: dict[str, Any] | None = None

    @property
    def type(self) -> str:
        return "audio" if self.audio is not None else str((self.event or {}).get("type"))


TURN_EVENTS = frozenset(
    {"speech_start", "speech_end", "end_of_turn", "interruption", "backchannel"}
)


class NexoraStream:
    """An open streaming session (Process or Relay mode)."""

    def __init__(self, ws: Any, started: dict[str, Any]) -> None:
        self._ws = ws
        self.started = started
        self.session_id: str = started.get("session_id", "")
        self.latency_ms: float = float(started.get("latency_ms", 0.0))
        self.summary: dict[str, Any] | None = None

    async def send_audio(self, chunk: bytes) -> None:
        await self._ws.send(chunk)

    async def set_agent_speaking(self, speaking: bool) -> None:
        """Process mode: tell Nexora your agent is playing audio (enables interruption events)."""
        await self._ws.send(json.dumps({"type": "agent_speaking", "value": speaking}))

    async def flush(self) -> None:
        await self._ws.send(json.dumps({"type": "flush"}))

    async def request_end(self) -> None:
        """Ask the server to flush and end the session. Keep iterating to receive the rest;
        ``summary`` is set when iteration finishes."""
        await self._ws.send(json.dumps({"type": "end"}))

    async def end(self) -> dict[str, Any] | None:
        """Finish gracefully when nothing else is reading the stream; returns the summary."""
        await self.request_end()
        async for _ in self:
            pass
        return self.summary

    async def __aiter__(self) -> AsyncIterator[Message]:
        import websockets

        try:
            async for raw in self._ws:
                if isinstance(raw, bytes):
                    yield Message(audio=raw)
                    continue
                msg = json.loads(raw)
                if msg.get("type") == "session.ended":
                    self.summary = msg
                    continue
                if msg.get("type") == "error":
                    raise NexoraError(msg.get("message", "error"), msg.get("code"))
                yield Message(event=msg)
        except websockets.ConnectionClosed as exc:
            code = exc.rcvd.code if exc.rcvd else None
            if code not in (1000, 1001, None):
                reason = exc.rcvd.reason if exc.rcvd else ""
                raise SessionClosed(code, reason, self.summary) from exc

    async def close(self) -> None:
        await self._ws.close()


class _StreamContext:
    def __init__(self, url: str, headers: dict[str, str]) -> None:
        self._url = url
        self._headers = headers
        self._stream: NexoraStream | None = None

    async def __aenter__(self) -> NexoraStream:
        import websockets

        ws = await websockets.connect(
            self._url, additional_headers=self._headers, max_size=16 * 1024 * 1024
        )
        first = json.loads(await ws.recv())
        if first.get("type") == "error":
            await ws.close()
            raise NexoraError(first.get("message", "rejected"), first.get("code"))
        self._stream = NexoraStream(ws, first)
        return self._stream

    async def __aexit__(
        self, et: type[BaseException] | None, e: BaseException | None, tb: TracebackType | None
    ) -> None:
        if self._stream is not None:
            await self._stream.close()


class NexoraClient:
    """Client for the Nexora REST API and streaming endpoints."""

    def __init__(self, base_url: str, api_key: str, timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._key = api_key
        self._http = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    @property
    def ws_base(self) -> str:
        return self.base_url.replace("https://", "wss://", 1).replace("http://", "ws://", 1)

    def stream(
        self,
        *,
        encoding: str = "pcm16",
        sample_rate: int = 16000,
        channels: int = 1,
        profile: str | None = None,
        output_encoding: str | None = None,
        output_sample_rate: int | None = None,
        relay_target: str | None = None,
    ) -> _StreamContext:
        """Open a session. With ``relay_target`` it uses Relay mode, otherwise Process mode."""
        q: dict[str, Any] = {"encoding": encoding, "sample_rate": sample_rate, "channels": channels}
        for k, v in (
            ("profile", profile),
            ("output_encoding", output_encoding),
            ("output_sample_rate", output_sample_rate),
            ("target", relay_target),
        ):
            if v is not None:
                q[k] = v
        path = "/v1/relay" if relay_target else "/v1/stream"
        return _StreamContext(
            f"{self.ws_base}{path}?{urlencode(q)}", {"Authorization": f"Bearer {self._key}"}
        )

    async def create_session_token(
        self,
        *,
        mode: str = "process",
        profile: str | None = None,
        relay_target: str | None = None,
        ttl_s: int | None = None,
    ) -> dict[str, Any]:
        body = {"mode": mode, "profile": profile, "relay_target": relay_target, "ttl_s": ttl_s}
        data: dict[str, Any] = await self._request("POST", "/v1/session-tokens", json=body)
        return data

    async def usage(self) -> dict[str, Any]:
        data: dict[str, Any] = await self._request("GET", "/v1/usage")
        return data

    async def sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        data: list[dict[str, Any]] = await self._request(
            "GET", "/v1/sessions", params={"limit": limit}
        )
        return data

    async def _request(self, method: str, path: str, **kw: Any) -> Any:
        r = await self._http.request(method, path, **kw)
        if r.status_code >= 400:
            try:
                detail = r.json().get("detail", r.text)
            except ValueError:
                detail = r.text
            raise NexoraError(str(detail), r.status_code)
        return r.json()

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self, et: type[BaseException] | None, e: BaseException | None, tb: TracebackType | None
    ) -> None:
        await self.aclose()
