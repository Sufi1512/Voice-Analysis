"""Double-submit CSRF: unsafe methods must echo the CSRF cookie in the X-CSRF-Token header."""

import hmac
import secrets

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

SESSION_COOKIE = "__Host-nexora_session"
CSRF_COOKIE = "__Host-nexora_csrf"
CSRF_HEADER = "X-CSRF-Token"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
COOKIE_MAX_AGE = 7 * 24 * 3600


def new_token() -> str:
    return secrets.token_urlsafe(32)


def set_csrf_cookie(response: Response, token: str) -> None:
    # Readable by the portal's script (it must copy it into the header), so not HttpOnly.
    response.set_cookie(CSRF_COOKIE, token, max_age=COOKIE_MAX_AGE, path="/", secure=True, samesite="lax")


class CsrfMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method not in SAFE_METHODS and request.url.path.startswith("/v1/"):
            cookie = request.cookies.get(CSRF_COOKIE, "")
            header = request.headers.get(CSRF_HEADER, "")
            if not cookie or not hmac.compare_digest(cookie.encode(), header.encode()):
                return JSONResponse(status_code=403, content={"error": "csrf_failed"})
        return await call_next(request)
