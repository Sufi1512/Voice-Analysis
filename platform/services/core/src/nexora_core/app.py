"""FastAPI application factory for NEXORA Core."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from nexora_core.api.auth import router as auth_router
from nexora_core.auth.csrf import CsrfMiddleware
from nexora_core.logging import configure_logging, get_logger
from nexora_core.settings import Settings

log = get_logger(__name__)
READY_TIMEOUT_S = 2.0


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app. Engines and connections are created here, never at import time."""
    settings = settings or Settings()
    configure_logging(settings.log_level)
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
        yield
        await engine.dispose()

    app = FastAPI(title="NEXORA Core", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.clock = lambda: datetime.now(UTC)
    app.add_middleware(CsrfMiddleware)
    app.include_router(auth_router)

    @app.exception_handler(HTTPException)
    async def http_error(_request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"error": exc.detail}, headers=exc.headers)

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", include_in_schema=False)
    async def readyz() -> JSONResponse:
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"), execution_options={"timeout": READY_TIMEOUT_S})
            database = "up"
        except Exception as exc:  # noqa: BLE001 - any failure means not ready
            log.warning("readiness check failed", check="database", error=type(exc).__name__)
            database = "down"
        ready = database == "up"
        return JSONResponse(
            status_code=200 if ready else 503,
            content={"status": "ready" if ready else "not_ready", "checks": {"database": database}},
        )

    return app
