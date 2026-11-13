"""WebSocket endpoints.

``/v1/stream`` (Process mode)
    The customer sends audio; Nexora sends back cleaned audio and turn events on the
    same socket.

``/v1/relay`` (Relay mode)
    The customer's caller connects here; Nexora forwards cleaned audio and events to the
    customer's agent WebSocket (allowlisted URL) and agent audio back to the caller.

Query parameters: ``encoding`` (pcm16|float32|mulaw|alaw|opus; opus = one packet per
binary message, input only), ``sample_rate``, ``channels``,
``output_encoding``, ``output_sample_rate``, ``profile``, ``target`` (relay), ``token``.
Auth: ``Authorization: Bearer <API key>`` with the ``stream`` scope, or ``token=<session token>``.

Client control messages (JSON text): ``{"type": "agent_speaking", "value": true}``,
``{"type": "agent_audio", "data": "<base64>"}`` (the agent audio just played to the caller,
in the stream's input format: the echo reference), ``{"type": "flush"}``, ``{"type": "reset"}``,
``{"type": "end"}``, ``{"type": "ping"}``.

Echo: in Relay mode the agent audio the server forwards to the caller is used as the echo
reference automatically; in Process mode send it with ``agent_audio``. With a reference,
the agent's own voice coming back is not reported as the caller speaking or interrupting,
and a profile with ``echo_cancellation: true`` also removes it from the audio.

Server messages: binary audio; JSON ``session.started``, turn events (``speech_start``,
``speech_end``, ``end_of_turn``, ``interruption``, ``backchannel``), ``pong``,
``session.ended`` (with usage) and ``error``.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import logging
import time
from collections import Counter
from dataclasses import dataclass
from typing import Any

import jwt
from fastapi import APIRouter, WebSocket
from nexora_audio import AudioFormat, AudioFormatError, StreamSession
from starlette.concurrency import run_in_threadpool
from starlette.websockets import WebSocketDisconnect, WebSocketState

from nexora_server.db import Database, Organization, SessionRecord, utcnow
from nexora_server.deps import bearer, principal_from_key
from nexora_server.observability import Metrics
from nexora_server.relay_policy import RelayTargetError, check_relay_target
from nexora_server.security import decode_session_token
from nexora_server.services import ServiceError, quota_remaining_s, resolve_profile
from nexora_server.settings import Settings
from nexora_server.streaming.manager import CapacityError, SessionManager, SessionSpec

log = logging.getLogger("nexora.stream")
router = APIRouter()


class RejectError(Exception):
    def __init__(self, code: int, reason: str, metric: str) -> None:
        super().__init__(reason)
        self.code, self.reason, self.metric = code, reason, metric


@dataclass
class StreamContext:
    org: Organization
    mode: str
    spec: SessionSpec
    profile_id: str | None
    api_key_id: str | None
    relay_target: str | None
    quota_left_s: float | None


def _fmt(params: dict[str, str], prefix: str = "", base: AudioFormat | None = None) -> AudioFormat:
    default = base.encoding if base and not base.packetized else "pcm16"
    enc = params.get(f"{prefix}encoding", default)
    rate = int(params.get(f"{prefix}sample_rate", base.sample_rate if base else 16000))
    ch = int(params.get("channels", base.channels if base else 1))
    return AudioFormat(enc, rate, ch)  # type: ignore[arg-type]


def _prepare(ws: WebSocket, mode: str, settings: Settings, db: Database) -> StreamContext:
    """Authenticate and resolve everything needed to start (runs in a worker thread)."""
    params = dict(ws.query_params)
    token = params.get("token")
    with db.session() as s:
        claims: dict[str, Any] = {}
        if token:
            try:
                claims = decode_session_token(settings.secret_key, token)
            except jwt.ExpiredSignatureError as exc:
                raise RejectError(4001, "session token expired", "token_expired") from exc
            except jwt.InvalidTokenError as exc:
                raise RejectError(4001, "invalid session token", "unauthorized") from exc
            if claims.get("mode") != mode:
                raise RejectError(4003, f"token is for {claims.get('mode')} mode", "forbidden")
            org_id, key_id = str(claims["sub"]), claims.get("kid")
        else:
            key = bearer(ws.headers.get("authorization"))
            who = principal_from_key(key, s, settings) if key else None
            if who is None or who.org_id is None:
                raise RejectError(4001, "missing or invalid API key", "unauthorized")
            if not who.has("stream"):
                raise RejectError(4003, "API key lacks the 'stream' scope", "forbidden")
            org_id, key_id = who.org_id, who.api_key_id

        org = s.get(Organization, org_id)
        if org is None or not org.active:
            raise RejectError(4003, "organization inactive", "forbidden")

        try:
            ref = claims.get("profile_id") if token else params.get("profile")
            prof = resolve_profile(s, org.id, ref)
        except ServiceError as exc:
            raise RejectError(4004, exc.message, "bad_request") from exc

        target = None
        if mode == "relay":
            target = claims.get("relay_target") if token else params.get("target")
            if not target:
                raise RejectError(4400, "relay mode needs a target agent URL", "bad_request")
            try:
                check_relay_target(target, org.relay_allowlist, settings.deployment_mode)
            except RelayTargetError as exc:
                raise RejectError(4003, str(exc), "relay_forbidden") from exc

        try:
            in_fmt = _fmt(params)
            out_fmt = _fmt(params, "output_", in_fmt)
        except (AudioFormatError, ValueError) as exc:
            raise RejectError(4400, f"bad audio format: {exc}", "bad_request") from exc

        left = quota_remaining_s(s, org)
        if left is not None and left <= 0:
            raise RejectError(4402, "monthly audio quota exhausted", "quota")
        spec = SessionSpec.build(
            in_fmt,
            out_fmt,
            dict(prof.audio_settings) if prof else {},
            (dict(prof.turn_settings) if prof.turn_settings is not None else None) if prof else {},
        )
        s.expunge(org)
        return StreamContext(org, mode, spec, prof.id if prof else None, key_id, target, left)


async def _send_json(ws: WebSocket, data: dict[str, Any]) -> None:
    if ws.application_state == WebSocketState.CONNECTED:
        await ws.send_text(json.dumps(data))


async def _close(ws: WebSocket, code: int, reason: str) -> None:
    if ws.application_state == WebSocketState.CONNECTED:
        with contextlib.suppress(RuntimeError, WebSocketDisconnect):
            await ws.close(code=code, reason=reason[:120])


class _Run:
    """Per-connection state shared by the processing loop and the relay pump."""

    def __init__(self, ctx: StreamContext, session: StreamSession) -> None:
        self.ctx = ctx
        self.session = session
        self.audio_s = 0.0
        self.events: Counter[str] = Counter()
        self.close_code = 1000
        self.close_reason = "normal"
        self.fmt = ctx.spec.input_format
        self.quality: dict[str, Any] = {}

    def account(self, nbytes: int) -> None:
        if self.fmt.packetized:  # Opus: count decoded audio, not bytes
            self.audio_s = self.session.input_seconds
        else:
            self.audio_s += nbytes / self.fmt.bytes_per_frame / self.fmt.sample_rate


@router.websocket("/v1/stream")
async def stream_endpoint(ws: WebSocket) -> None:
    await _serve(ws, "process")


@router.websocket("/v1/relay")
async def relay_endpoint(ws: WebSocket) -> None:
    await _serve(ws, "relay")


async def _serve(ws: WebSocket, mode: str) -> None:
    app = ws.app
    settings: Settings = app.state.settings
    db: Database = app.state.db
    mgr: SessionManager = app.state.manager
    metrics: Metrics = app.state.metrics
    await ws.accept()
    try:
        ctx = await run_in_threadpool(_prepare, ws, mode, settings, db)
    except RejectError as r:
        metrics.rejections.labels(r.metric).inc()
        await _send_json(ws, {"type": "error", "code": r.code, "message": r.reason})
        await _close(ws, r.code, r.reason)
        return

    try:
        slot = mgr.slot(ctx.org.id, ctx.org.max_concurrent_sessions)
        slot.__enter__()
    except CapacityError as c:
        metrics.rejections.labels("capacity" if c.code == 1013 else "org_limit").inc()
        await _send_json(ws, {"type": "error", "code": c.code, "message": c.reason})
        await _close(ws, c.code, c.reason)
        return

    record_id: str | None = None
    session: StreamSession | None = None
    run: _Run | None = None
    healthy = True
    metrics.active.labels(mode).inc()
    try:
        t0 = time.perf_counter()
        session = await mgr.acquire(ctx.spec)
        metrics.session_start_seconds.observe(time.perf_counter() - t0)
        run = _Run(ctx, session)
        record_id = await run_in_threadpool(_create_record, db, ctx, session)
        log.info(
            "session started",
            extra={
                "session_id": record_id,
                "org_id": ctx.org.id,
                "mode": mode,
                "backends": session.backends,
            },
        )
        await _send_json(
            ws,
            {
                "type": "session.started",
                "session_id": record_id,
                "mode": mode,
                "backends": session.backends,
                "latency_ms": round(session.latency_ms, 1),
                "input_format": _fmt_dict(ctx.spec.input_format),
                "output_format": _fmt_dict(ctx.spec.output_format),
            },
        )
        if mode == "process":
            await _process_loop(ws, run, settings, metrics, db)
        else:
            await _relay_loop(ws, run, settings, metrics, db)
    except Exception:
        healthy = False
        log.exception("session failed", extra={"session_id": record_id, "org_id": ctx.org.id})
        if run is not None:
            run.close_code, run.close_reason = 1011, "internal error"
        await _send_json(ws, {"type": "error", "code": 1011, "message": "internal error"})
    finally:
        metrics.active.labels(mode).dec()
        slot.__exit__(None, None, None)
        if run is not None:
            metrics.audio_seconds.labels(mode).inc(run.audio_s)
            outcome = "ok" if run.close_code in (1000, 1001) else "error"
            metrics.sessions.labels(mode, outcome).inc()
            run.quality = run.session.quality()
            metrics.observe_quality(run.quality)
            await _send_json(
                ws,
                {
                    "type": "session.ended",
                    "session_id": record_id,
                    "audio_seconds": round(run.audio_s, 3),
                    "events": dict(run.events),
                    "close_code": run.close_code,
                    "reason": run.close_reason,
                    "quality": run.quality,
                },
            )
            if record_id:
                await run_in_threadpool(_finish_record, db, record_id, run, healthy)
            log.info(
                "session ended",
                extra={
                    "session_id": record_id,
                    "org_id": ctx.org.id,
                    "mode": mode,
                    "audio_seconds": round(run.audio_s, 3),
                    "close_code": run.close_code,
                    "quality": run.quality,
                },
            )
            await _close(ws, run.close_code, run.close_reason)
        if session is not None:
            mgr.release(ctx.spec, session, healthy)


def _fmt_dict(f: AudioFormat) -> dict[str, Any]:
    return {"encoding": f.encoding, "sample_rate": f.sample_rate, "channels": f.channels}


def _create_record(db: Database, ctx: StreamContext, session: StreamSession) -> str:
    with db.session() as s:
        rec = SessionRecord(
            org_id=ctx.org.id,
            profile_id=ctx.profile_id,
            api_key_id=ctx.api_key_id,
            mode=ctx.mode,
            input_format=_fmt_dict(ctx.spec.input_format),
            backends=session.backends,
        )
        s.add(rec)
        s.flush()
        return rec.id


def _finish_record(db: Database, record_id: str, run: _Run, healthy: bool) -> None:
    with db.session() as s:
        rec = s.get(SessionRecord, record_id)
        if rec is None:
            return
        rec.status = "ended" if healthy else "failed"
        rec.audio_seconds = run.audio_s
        rec.event_counts = dict(run.events)
        rec.p99_processing_ms = round(run.session.timing.p99_ms, 3)
        rec.close_code = run.close_code
        rec.close_reason = run.close_reason
        rec.quality = run.quality
        rec.ended_at = utcnow()


async def _receive(ws: WebSocket, settings: Settings) -> dict[str, Any] | None:
    try:
        raw: Any = await asyncio.wait_for(ws.receive(), settings.idle_timeout_s)
    except TimeoutError:
        return {"type": "_idle"}
    msg: dict[str, Any] = dict(raw)
    if msg["type"] == "websocket.disconnect":
        return None
    return msg


async def _quota_ok(run: _Run, db: Database, settings: Settings, checked: list[float]) -> bool:
    """Re-check the org quota every ``quota_check_interval_s`` of audio."""
    if run.ctx.quota_left_s is None:
        return True
    if run.audio_s - checked[0] < settings.quota_check_interval_s:
        return run.audio_s < run.ctx.quota_left_s
    checked[0] = run.audio_s

    def remaining() -> float | None:
        with db.session() as s:
            org = s.get(Organization, run.ctx.org.id)
            return quota_remaining_s(s, org) if org else 0.0

    left = await run_in_threadpool(remaining)
    # usage of this session is not yet in the DB, so compare against what it has used
    return left is None or run.audio_s < left


async def _handle_audio(
    run: _Run, data: bytes, metrics: Metrics, executor: Any
) -> tuple[bytes, list[dict[str, Any]]]:
    loop = asyncio.get_running_loop()
    t0 = time.perf_counter()
    out = await loop.run_in_executor(executor, run.session.process, data)
    metrics.chunk_seconds.observe(time.perf_counter() - t0)
    run.account(len(data))
    events = []
    for ev in out.events:
        run.events[ev.type] += 1
        metrics.events.labels(ev.type).inc()
        events.append(ev.to_dict())
    return out.audio, events


async def _control(run: _Run, text: str) -> tuple[str, dict[str, Any] | None]:
    """Handle a client JSON control message. Returns (action, reply)."""
    try:
        msg = json.loads(text)
        kind = msg.get("type") if isinstance(msg, dict) else None
    except ValueError:
        return "error", {"type": "error", "code": 4400, "message": "invalid JSON"}
    if kind == "agent_speaking":
        run.session.set_agent_speaking(bool(msg.get("value")))
        return "ok", None
    if kind == "agent_audio":
        try:
            ref = base64.b64decode(str(msg.get("data", "")), validate=True)
        except (ValueError, TypeError):
            return "error", {
                "type": "error",
                "code": 4400,
                "message": "agent_audio.data must be base64",
            }
        if not run.fmt.packetized:
            await asyncio.get_running_loop().run_in_executor(
                None, run.session.push_reference, ref, run.fmt
            )
        return "ok", None
    if kind == "ping":
        return "ok", {"type": "pong", "audio_seconds": round(run.audio_s, 3)}
    if kind in ("flush", "end", "reset"):
        return kind, None
    return "forward", msg


async def _process_loop(
    ws: WebSocket, run: _Run, settings: Settings, metrics: Metrics, db: Database
) -> None:
    executor = ws.app.state.manager.executor
    quota_mark = [0.0]
    while True:
        msg = await _receive(ws, settings)
        if msg is None:
            run.close_code, run.close_reason = 1000, "client disconnected"
            return
        if msg["type"] == "_idle":
            run.close_code, run.close_reason = 4408, "idle timeout"
            return
        data, text = msg.get("bytes"), msg.get("text")
        if data is not None:
            if len(data) > settings.max_message_bytes:
                run.close_code, run.close_reason = 1009, "message too big"
                return
            audio, events = await _handle_audio(run, data, metrics, executor)
            if audio:
                await ws.send_bytes(audio)
            for ev in events:
                await _send_json(ws, ev)
            if not await _quota_ok(run, db, settings, quota_mark):
                run.close_code, run.close_reason = 4402, "monthly audio quota exhausted"
                return
        elif text is not None:
            action, reply = await _control(run, text)
            if reply is not None and action != "forward":
                await _send_json(ws, reply)
            if action in ("flush", "end"):
                out = await asyncio.get_running_loop().run_in_executor(executor, run.session.flush)
                if out.audio:
                    await ws.send_bytes(out.audio)
                for te in out.events:
                    run.events[te.type] += 1
                    await _send_json(ws, te.to_dict())
                if action == "end":
                    run.close_code, run.close_reason = 1000, "client ended session"
                    return
            elif action == "reset":
                await asyncio.get_running_loop().run_in_executor(executor, run.session.reset)


async def _relay_loop(
    ws: WebSocket, run: _Run, settings: Settings, metrics: Metrics, db: Database
) -> None:
    import websockets

    assert run.ctx.relay_target is not None
    # re-check right before connecting (DNS may have changed since the token was minted)
    check_relay_target(run.ctx.relay_target, run.ctx.org.relay_allowlist, settings.deployment_mode)
    try:
        agent = await websockets.connect(
            run.ctx.relay_target, open_timeout=10, max_size=settings.max_message_bytes * 4
        )
    except (OSError, websockets.InvalidHandshake, TimeoutError) as exc:
        run.close_code, run.close_reason = 4502, f"could not reach agent: {type(exc).__name__}"
        return

    executor = ws.app.state.manager.executor
    last_agent_audio = [0.0]
    quota_mark = [0.0]

    async def client_to_agent() -> None:
        while True:
            msg = await _receive(ws, settings)
            if msg is None:
                run.close_code, run.close_reason = 1000, "client disconnected"
                break
            if msg["type"] == "_idle":
                run.close_code, run.close_reason = 4408, "idle timeout"
                break
            data, text = msg.get("bytes"), msg.get("text")
            if data is not None:
                if len(data) > settings.max_message_bytes:
                    run.close_code, run.close_reason = 1009, "message too big"
                    break
                audio, events = await _handle_audio(run, data, metrics, executor)
                if audio:
                    await agent.send(audio)
                for ev in events:
                    await agent.send(json.dumps(ev))
                    if ev["type"] == "interruption":
                        await _send_json(ws, {"type": "interruption", "time_ms": ev["time_ms"]})
                if not await _quota_ok(run, db, settings, quota_mark):
                    run.close_code, run.close_reason = 4402, "monthly audio quota exhausted"
                    break
            elif text is not None:
                action, reply = await _control(run, text)
                if action == "forward" and reply is not None:
                    await agent.send(json.dumps(reply))
                elif reply is not None:
                    await _send_json(ws, reply)
                if action == "end":
                    run.close_code, run.close_reason = 1000, "client ended session"
                    break
        tail = await asyncio.get_running_loop().run_in_executor(executor, run.session.flush)
        with contextlib.suppress(websockets.ConnectionClosed):
            if tail.audio:
                await agent.send(tail.audio)
            for te in tail.events:
                run.events[te.type] += 1
                await agent.send(json.dumps(te.to_dict()))

    async def agent_to_client() -> None:
        try:
            async for msg in agent:
                if isinstance(msg, bytes):
                    last_agent_audio[0] = time.monotonic()
                    run.session.set_agent_speaking(True)
                    if not run.fmt.packetized:  # the agent audio is the echo reference
                        await asyncio.get_running_loop().run_in_executor(
                            None, run.session.push_reference, msg, run.fmt
                        )
                    if ws.application_state == WebSocketState.CONNECTED:
                        await ws.send_bytes(msg)
                else:
                    with contextlib.suppress(ValueError, TypeError, AttributeError):
                        data = json.loads(msg)
                        if data.get("type") == "agent_speaking":
                            run.session.set_agent_speaking(bool(data.get("value")))
                    if ws.application_state == WebSocketState.CONNECTED:
                        await ws.send_text(msg)
        except websockets.ConnectionClosed:
            pass
        if run.close_reason == "normal":
            run.close_code, run.close_reason = 1000, "agent closed the connection"

    async def agent_silence_watch() -> None:
        while True:
            await asyncio.sleep(0.05)
            last = last_agent_audio[0]
            if last and (time.monotonic() - last) * 1000 > settings.agent_silence_ms:
                run.session.set_agent_speaking(False)
                last_agent_audio[0] = 0.0

    tasks = {
        asyncio.create_task(client_to_agent()): "client",
        asyncio.create_task(agent_to_client()): "agent",
    }
    watcher = asyncio.create_task(agent_silence_watch())
    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        if any(tasks[t] == "client" for t in done):
            await agent.close()
            await asyncio.wait(pending, timeout=5)
        for t in done:
            err = t.exception()
            if err is not None and not isinstance(err, websockets.ConnectionClosed):
                raise err
    finally:
        watcher.cancel()
        for t in tasks:
            t.cancel()
        await asyncio.gather(watcher, *tasks, return_exceptions=True)
        with contextlib.suppress(Exception):
            await agent.close()
