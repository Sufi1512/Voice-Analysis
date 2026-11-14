"""/v1/auth: CSRF bootstrap, login, logout, logout everywhere; /v1/me."""

import math

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import text

from nexora_core.api.deps import Conn, CurrentSession, Now
from nexora_core.auth import throttle
from nexora_core.auth.csrf import COOKIE_MAX_AGE, CSRF_COOKIE, SESSION_COOKIE, new_token, set_csrf_cookie
from nexora_core.auth.passwords import hash_password, needs_rehash, verify_password
from nexora_core.auth.sessions import create_session, hash_session_id, revoke_all_sessions, revoke_session
from nexora_core.logging import get_logger

log = get_logger(__name__)
router = APIRouter(prefix="/v1")
INVALID = {"error": "invalid_credentials"}


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)

    def __repr__(self) -> str:  # never print the password, even in tracebacks
        return f"LoginRequest(email={self.email!r})"


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.get("/auth/csrf", status_code=204)
async def csrf_bootstrap(request: Request, response: Response) -> None:
    if CSRF_COOKIE not in request.cookies:
        set_csrf_cookie(response, new_token())


@router.post("/auth/login", response_model=None)
async def login(body: LoginRequest, request: Request, conn: Conn, at: Now) -> JSONResponse:
    ip = _client_ip(request)
    email_key = throttle.key(throttle.EMAIL, body.email)
    ip_key = throttle.key(throttle.IP, ip) if ip else None
    keys = [k for k in (email_key, ip_key) if k]

    until = await throttle.locked_until(conn, keys, now=at)
    if until is not None:
        retry = max(1, math.ceil((until - at).total_seconds()))
        return JSONResponse(status_code=429, content={"error": "locked"}, headers={"Retry-After": str(retry)})

    user = (
        (
            await conn.execute(
                text(
                    "SELECT id, email, name, password_hash, status, mfa_enabled_at"
                    " FROM users WHERE email = :e"
                ),
                {"e": body.email.strip()},
            )
        )
        .mappings()
        .first()
    )
    ok = verify_password(user["password_hash"] if user else None, body.password)
    if not ok or user is None or user["status"] != "active":
        await throttle.record_failure(conn, email_key, throttle.EMAIL, now=at)
        if ip_key:
            await throttle.record_failure(conn, ip_key, throttle.IP, now=at)
        log.info("login failed", reason="invalid_credentials")
        return JSONResponse(status_code=401, content=INVALID)

    await throttle.clear(conn, email_key)
    if previous := request.cookies.get(SESSION_COOKIE):  # no session fixation, no stale sessions
        await revoke_session(conn, hash_session_id(previous), now=at)
    if needs_rehash(user["password_hash"]):
        await conn.execute(
            text("UPDATE users SET password_hash = :h WHERE id = :i"),
            {"h": hash_password(body.password), "i": user["id"]},
        )
    await conn.execute(
        text("UPDATE users SET last_login_at = :now WHERE id = :i"), {"now": at, "i": user["id"]}
    )
    raw = await create_session(
        conn, user_id=user["id"], now=at, ip=ip, user_agent=request.headers.get("user-agent")
    )
    log.info("login succeeded", user_id=user["id"])

    response = JSONResponse(
        content={
            "user": {"id": user["id"], "email": user["email"], "name": user["name"]},
            "mfa_required": user["mfa_enabled_at"] is not None,
        }
    )
    response.set_cookie(
        SESSION_COOKIE, raw, max_age=COOKIE_MAX_AGE, path="/", secure=True, httponly=True, samesite="lax"
    )
    set_csrf_cookie(response, new_token())  # rotate on privilege change
    return response


def _clear_cookies(response: Response) -> None:
    for name in (SESSION_COOKIE, CSRF_COOKIE):
        response.delete_cookie(name, path="/", secure=True, samesite="lax")


@router.post("/auth/logout", status_code=204)
async def logout(session: CurrentSession, conn: Conn, at: Now, response: Response) -> None:
    await revoke_session(conn, session.id_hash, now=at)
    _clear_cookies(response)


@router.post("/auth/logout-all", status_code=204)
async def logout_all(session: CurrentSession, conn: Conn, at: Now, response: Response) -> None:
    count = await revoke_all_sessions(conn, session.user_id, now=at)
    log.info("logged out everywhere", user_id=session.user_id, sessions=count)
    _clear_cookies(response)


@router.get("/me")
async def me(session: CurrentSession, conn: Conn) -> dict:
    user = (
        (await conn.execute(text("SELECT id, email, name FROM users WHERE id = :i"), {"i": session.user_id}))
        .mappings()
        .one()
    )
    return {"user": dict(user), "mfa_passed": session.mfa_passed_at is not None}
