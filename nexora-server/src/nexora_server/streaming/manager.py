"""Capacity limits, the processing thread pool and a warm pool of audio sessions."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections import defaultdict
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from nexora_audio import AudioFormat, StreamSession, TurnConfig

log = logging.getLogger("nexora.manager")


@dataclass(frozen=True)
class SessionSpec:
    """Everything that decides how an audio session is built (the pool key)."""

    input_format: AudioFormat
    output_format: AudioFormat
    audio_settings: tuple[tuple[str, Any], ...] = ()
    turn_settings: tuple[tuple[str, Any], ...] | None = ()

    @classmethod
    def build(
        cls,
        input_format: AudioFormat,
        output_format: AudioFormat | None,
        audio_settings: dict[str, Any],
        turn_settings: dict[str, Any] | None,
    ) -> SessionSpec:
        def freeze(d: dict[str, Any]) -> tuple[tuple[str, Any], ...]:
            return tuple(sorted((k, json.dumps(v, sort_keys=True)) for k, v in d.items()))

        return cls(
            input_format,
            output_format or input_format,
            freeze(audio_settings),
            None if turn_settings is None else freeze(turn_settings),
        )

    def create(self) -> StreamSession:
        audio = {k: json.loads(v) for k, v in self.audio_settings}
        turns = (
            None
            if self.turn_settings is None
            else TurnConfig(**{k: json.loads(v) for k, v in self.turn_settings})
        )
        return StreamSession(
            input_format=self.input_format,
            output_format=self.output_format,
            turns=turns,
            **audio,
        )


class CapacityError(Exception):
    def __init__(self, code: int, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


@dataclass
class _Pool:
    idle: list[StreamSession] = field(default_factory=list)


class SessionManager:
    """Owns the worker threads, enforces capacity, and keeps warm sessions ready.

    Creating a session loads models (0.1-0.8 s), so recently used session types are kept
    in a small pool. Returned sessions are reset in the background before reuse.
    """

    def __init__(self, max_sessions: int, worker_threads: int, pool_size: int = 2) -> None:
        self.max_sessions = max_sessions
        self.pool_size = pool_size
        self.executor = ThreadPoolExecutor(worker_threads, thread_name_prefix="nexora-audio")
        self._lock = threading.Lock()
        self._active = 0
        self._per_org: dict[str, int] = defaultdict(int)
        self._pools: dict[SessionSpec, _Pool] = defaultdict(_Pool)

    # -- capacity --------------------------------------------------------------------

    @property
    def active(self) -> int:
        return self._active

    def active_for(self, org_id: str) -> int:
        return self._per_org.get(org_id, 0)

    @contextmanager
    def slot(self, org_id: str, org_limit: int) -> Iterator[None]:
        with self._lock:
            if self._active >= self.max_sessions:
                raise CapacityError(1013, "server at capacity, retry another instance")
            if self._per_org[org_id] >= org_limit:
                raise CapacityError(4429, f"organization limit of {org_limit} concurrent sessions")
            self._active += 1
            self._per_org[org_id] += 1
        try:
            yield
        finally:
            with self._lock:
                self._active -= 1
                self._per_org[org_id] -= 1
                if self._per_org[org_id] <= 0:
                    del self._per_org[org_id]

    # -- session pool ----------------------------------------------------------------

    async def acquire(self, spec: SessionSpec) -> StreamSession:
        with self._lock:
            pool = self._pools[spec]
            if pool.idle:
                return pool.idle.pop()
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self.executor, spec.create)

    def release(self, spec: SessionSpec, session: StreamSession, healthy: bool = True) -> None:
        """Return a session: it is reset in the background and kept if the pool has room."""
        if not healthy or session.closed:
            self.executor.submit(session.close)
            return

        def recycle() -> None:
            try:
                session.reset()
            except Exception:
                log.exception("session reset failed; discarding")
                session.close()
                return
            with self._lock:
                pool = self._pools[spec]
                if len(pool.idle) < self.pool_size:
                    pool.idle.append(session)
                    return
            session.close()

        self.executor.submit(recycle)

    def prewarm(self, spec: SessionSpec, count: int | None = None) -> None:
        """Create sessions for ``spec`` ahead of time (blocking)."""
        for _ in range(count if count is not None else self.pool_size):
            s = spec.create()
            with self._lock:
                self._pools[spec].idle.append(s)

    def idle_sessions(self) -> int:
        with self._lock:
            return sum(len(p.idle) for p in self._pools.values())

    def shutdown(self) -> None:
        with self._lock:
            sessions = [s for p in self._pools.values() for s in p.idle]
            self._pools.clear()
        for s in sessions:
            s.close()
        self.executor.shutdown(wait=True, cancel_futures=True)
