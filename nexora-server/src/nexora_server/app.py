"""Application factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import nexora_audio
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from nexora_audio import AudioFormat
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.concurrency import run_in_threadpool

from nexora_server.api.routes import router as api_router
from nexora_server.db import Database
from nexora_server.observability import Metrics, setup_logging
from nexora_server.settings import Settings
from nexora_server.streaming.manager import SessionManager, SessionSpec
from nexora_server.streaming.ws import router as ws_router

log = logging.getLogger("nexora.app")
DEFAULT_SPEC = SessionSpec.build(AudioFormat("pcm16", 16000), None, {}, {})


def create_app(settings: Settings | None = None, *, prewarm: bool = True) -> FastAPI:
    settings = settings or Settings.from_env()
    setup_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.db.create_all()
        if prewarm:  # load models before taking traffic; readiness waits for this
            await run_in_threadpool(app.state.manager.prewarm, DEFAULT_SPEC)
        app.state.ready = True
        log.info(
            "ready", extra={"capacity": settings.max_sessions, "mode": settings.deployment_mode}
        )
        yield
        app.state.ready = False
        app.state.manager.shutdown()

    app = FastAPI(
        title="Nexora Voice Cloud",
        version="0.1.0",
        description="Real-time voice processing for AI agents: noise removal, enhancement, "
        "voice activity and turn events over WebSocket.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.db = Database(settings.database_url)
    app.state.metrics = Metrics()
    app.state.metrics.capacity.set(settings.max_sessions)
    app.state.manager = SessionManager(settings.max_sessions, settings.worker_threads)
    app.state.ready = False

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["*"],
            allow_headers=["authorization", "content-type"],
        )

    app.include_router(api_router)
    app.include_router(ws_router)

    @app.get("/healthz", tags=["ops"])
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", tags=["ops"])
    def readyz(request: Request) -> Response:
        state = request.app.state
        checks = {"started": bool(state.ready)}
        try:
            checks["database"] = state.db.ping()
        except Exception:
            checks["database"] = False
        mgr: SessionManager = state.manager
        checks["has_capacity"] = mgr.active < mgr.max_sessions
        ok = all(checks.values())
        body = {
            "status": "ready" if ok else "not ready",
            "checks": checks,
            "active_sessions": mgr.active,
            "capacity": mgr.max_sessions,
            "warm_sessions": mgr.idle_sessions(),
            "engine": {"nexora_audio": nexora_audio.__version__},
        }
        return JSONResponse(body, status_code=200 if ok else 503)

    @app.get("/metrics", tags=["ops"], include_in_schema=False)
    def metrics(request: Request) -> Response:
        data = generate_latest(request.app.state.metrics.registry)
        return Response(data, media_type=CONTENT_TYPE_LATEST)

    return app
