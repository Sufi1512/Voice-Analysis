"""FastAPI application factory for NEXORA Core."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from nexora_core.api.auth import router as auth_router
from nexora_core.api.organizations import router as organizations_router
from nexora_core.api.platform import router as platform_router
from nexora_core.auth.csrf import CsrfMiddleware
from nexora_core.bootstrap import bootstrap_platform_owner
from nexora_core.logging import configure_logging, get_logger
from nexora_core.settings import Settings

log = get_logger(__name__)
ROUTERS: tuple[APIRouter, ...] = (auth_router, organizations_router, platform_router)
READY_TIMEOUT_S = 2.0


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app. Engines and connections are created here, never at import time."""
    settings = settings or Settings()
    configure_logging(settings.log_level)
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
        await bootstrap_platform_owner(
            engine,
            email=settings.bootstrap_owner_email,
            token_file=Path(settings.bootstrap_token_file),
            now=datetime.now(UTC),
        )
        yield
        await engine.dispose()

    app = FastAPI(title="NEXORA Core", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.clock = lambda: datetime.now(UTC)
    app.add_middleware(CsrfMiddleware)
    app.state.routers = ROUTERS
    for router in ROUTERS:
        app.include_router(router)

    @app.exception_handler(HTTPException)
    async def http_error(_request: Request, exc: HTTPException) -> JSONResponse:
        content = exc.detail if isinstance(exc.detail, dict) else {"error": exc.detail}
        return JSONResponse(status_code=exc.status_code, content=content, headers=exc.headers)

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


def api_routes(app: FastAPI) -> list[APIRoute]:
    """Every /v1 route the app serves (the single list it mounts), for authorization tests."""
    return [r for router in app.state.routers for r in router.routes if isinstance(r, APIRoute)]
