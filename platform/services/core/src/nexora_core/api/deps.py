"""Request dependencies: clock, database transaction, current session."""

from collections.abc import AsyncGenerator, Callable
from datetime import datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from nexora_core.auth.csrf import SESSION_COOKIE
from nexora_core.auth.sessions import Session, resolve_session


def now(request: Request) -> datetime:
    clock: Callable[[], datetime] = request.app.state.clock
    return clock()


async def transaction(request: Request) -> AsyncGenerator[AsyncConnection]:
    """One transaction per request: committed on success, rolled back on any error."""
    engine: AsyncEngine = request.app.state.engine
    async with engine.begin() as conn:
        yield conn


Now = Annotated[datetime, Depends(now)]
Conn = Annotated[AsyncConnection, Depends(transaction)]


async def current_session(request: Request, conn: Conn, at: Now) -> Session:
    raw = request.cookies.get(SESSION_COOKIE)
    session = await resolve_session(conn, raw, now=at) if raw else None
    if session is None:
        raise HTTPException(status_code=401, detail="unauthenticated")
    return session


CurrentSession = Annotated[Session, Depends(current_session)]
