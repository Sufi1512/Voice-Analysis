"""FastAPI dependencies: settings, database sessions and the authenticated principal."""

from __future__ import annotations

import hmac
from collections.abc import Callable, Iterator

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from nexora_server.db import Database
from nexora_server.security import Principal
from nexora_server.services import authenticate_key
from nexora_server.settings import Settings


def get_settings(request: Request) -> Settings:
    s: Settings = request.app.state.settings
    return s


def get_db(request: Request) -> Iterator[Session]:
    database: Database = request.app.state.db
    with database.session() as s:
        yield s


def bearer(header: str | None) -> str | None:
    if not header:
        return None
    scheme, _, value = header.partition(" ")
    return value.strip() if scheme.lower() == "bearer" and value.strip() else None


def principal_from_key(plaintext: str, db: Session, settings: Settings) -> Principal | None:
    if settings.admin_api_key and hmac.compare_digest(plaintext, settings.admin_api_key):
        return Principal(None, frozenset(), "superadmin")
    return authenticate_key(db, plaintext, settings.secret_key)


def get_principal(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Principal:
    key = bearer(request.headers.get("authorization"))
    if key is None:
        from nexora_server.sso import principal_from_cookie

        session = principal_from_cookie(request, db, settings)
        if session is not None:
            return session
        raise HTTPException(401, "missing bearer API key", headers={"WWW-Authenticate": "Bearer"})
    who = principal_from_key(key, db, settings)
    if who is None:
        raise HTTPException(401, "invalid API key", headers={"WWW-Authenticate": "Bearer"})
    return who


def require(scope: str) -> Callable[[Principal], Principal]:
    def check(who: Principal = Depends(get_principal)) -> Principal:
        if not who.has(scope):
            raise HTTPException(403, f"API key lacks the '{scope}' scope")
        return who

    return check


def require_superadmin(who: Principal = Depends(get_principal)) -> Principal:
    if not who.is_superadmin:
        raise HTTPException(403, "super-admin only")
    return who


def org_for(who: Principal, org_id: str | None) -> str:
    """Org the request acts on: the caller's own, or any (super-admin must name it)."""
    if who.is_superadmin:
        if not org_id:
            raise HTTPException(422, "super-admin must pass org_id")
        return org_id
    if who.org_id is None:  # explicit: asserts vanish under python -O
        raise HTTPException(403, "no organization for this credential")
    if org_id and org_id != who.org_id:
        raise HTTPException(403, "cannot act on another organization")
    return who.org_id
