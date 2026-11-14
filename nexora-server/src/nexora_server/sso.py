"""Single sign-on for the dashboard with OpenID Connect (E9).

Works with any OIDC provider (Google Workspace, Microsoft Entra ID, Okta, Auth0, Keycloak):

1. ``GET /auth/oidc/login``: redirect to the provider with ``state``, ``nonce`` and a PKCE
   S256 challenge. Those three live only in a short-lived signed HttpOnly cookie.
2. ``GET /auth/oidc/callback``: check ``state``, exchange the code (with the PKCE verifier),
   verify the ID token (signature from the provider's JWKS, issuer, audience, expiry,
   nonce) and require a verified email that is a member of an organization
   (``sso_members``, managed by the organization's admins) or listed in
   ``NEXORA_SSO_SUPERADMIN_EMAILS``.
3. The dashboard session is a signed cookie (``SameSite=Strict``, HttpOnly, 8 hours).
   Requests that use it must also send ``X-Nexora-CSRF: 1``, which other sites cannot
   add. Membership is checked again on every request, so removing someone takes effect at
   once.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
from typing import Any
from urllib.parse import urlencode

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from nexora_server.db import Database, SsoMember, utcnow
from nexora_server.security import Principal
from nexora_server.settings import Settings

SESSION_COOKIE = "nexora_session"
STATE_COOKIE = "nexora_oidc_state"
CSRF_HEADER = "x-nexora-csrf"
_SESSION_AUD = "nexora:dashboard"
_STATE_AUD = "nexora:oidc-state"
ROLE_SCOPES = {"admin": frozenset({"admin", "usage:read"}), "viewer": frozenset({"usage:read"})}

router = APIRouter(include_in_schema=False)


class OidcError(Exception):
    pass


class OidcProvider:
    """Discovery and JWKS from the issuer, cached; token exchange and ID-token checks."""

    def __init__(self, settings: Settings, http: Any = None) -> None:
        import httpx

        self.s = settings
        self.http = http or httpx.Client(timeout=10.0)
        self._meta: dict[str, Any] | None = None
        self._jwks: dict[str, Any] | None = None
        self._jwks_at = 0.0

    def meta(self) -> dict[str, Any]:
        if self._meta is None:
            url = self.s.oidc_issuer.rstrip("/") + "/.well-known/openid-configuration"
            r = self.http.get(url)
            r.raise_for_status()
            meta = r.json()
            if meta.get("issuer", "").rstrip("/") != self.s.oidc_issuer.rstrip("/"):
                raise OidcError("discovery issuer does not match NEXORA_OIDC_ISSUER")
            self._meta = meta
        return self._meta

    def _key(self, kid: str | None) -> Any:
        for attempt in range(2):  # refetch once if the key rotated
            if self._jwks is None or attempt or time.time() - self._jwks_at > 3600:
                r = self.http.get(self.meta()["jwks_uri"])
                r.raise_for_status()
                self._jwks, self._jwks_at = r.json(), time.time()
            for k in self._jwks.get("keys", []):
                if kid is None or k.get("kid") == kid:
                    return jwt.PyJWK(k).key
        raise OidcError("signing key not found")

    def authorize_url(self, state: str, nonce: str, challenge: str) -> str:
        q = {
            "response_type": "code",
            "client_id": self.s.oidc_client_id,
            "redirect_uri": self.s.oidc_redirect_url,
            "scope": "openid email profile",
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        return f"{self.meta()['authorization_endpoint']}?{urlencode(q)}"

    def exchange(self, code: str, verifier: str) -> dict[str, Any]:
        r = self.http.post(
            self.meta()["token_endpoint"],
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.s.oidc_redirect_url,
                "client_id": self.s.oidc_client_id,
                "client_secret": self.s.oidc_client_secret,
                "code_verifier": verifier,
            },
            headers={"Accept": "application/json"},
        )
        if r.status_code != 200:
            raise OidcError(f"token endpoint answered {r.status_code}")
        body: dict[str, Any] = r.json()
        return body

    def verify_id_token(self, token: str, nonce: str) -> dict[str, Any]:
        header = jwt.get_unverified_header(token)
        if header.get("alg") not in ("RS256", "ES256", "PS256"):
            raise OidcError("unsupported ID token algorithm")
        claims: dict[str, Any] = jwt.decode(
            token,
            self._key(header.get("kid")),
            algorithms=[header["alg"]],
            audience=self.s.oidc_client_id,
            issuer=self.meta()["issuer"],
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            leeway=60,
        )
        if not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
            raise OidcError("nonce mismatch")
        return claims


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _cookie_kwargs(settings: Settings) -> dict[str, Any]:
    return {"httponly": True, "secure": settings.cookie_secure, "path": "/"}


def provider(request: Request) -> OidcProvider:
    p = getattr(request.app.state, "oidc", None)
    if p is None:
        raise HTTPException(404, "single sign-on is not configured")
    assert isinstance(p, OidcProvider)
    return p


@router.get("/auth/oidc/status")
def oidc_status(request: Request) -> dict[str, bool]:
    return {"enabled": getattr(request.app.state, "oidc", None) is not None}


@router.get("/auth/oidc/login")
def oidc_login(request: Request, p: OidcProvider = Depends(provider)) -> Response:
    settings: Settings = request.app.state.settings
    state, nonce = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(48)
    challenge = _b64(hashlib.sha256(verifier.encode()).digest())
    try:
        url = p.authorize_url(state, nonce, challenge)
    except Exception as exc:
        raise HTTPException(502, "identity provider unreachable") from exc
    signed = jwt.encode(
        {"aud": _STATE_AUD, "st": state, "n": nonce, "v": verifier, "exp": int(time.time()) + 600},
        settings.secret_key,
        algorithm="HS256",
    )
    resp = RedirectResponse(url, status_code=302)
    # Lax: the provider's redirect back is a cross-site top-level navigation
    resp.set_cookie(STATE_COOKIE, signed, max_age=600, samesite="lax", **_cookie_kwargs(settings))
    return resp


def _fail(status: int, message: str) -> Response:
    resp = JSONResponse({"detail": message}, status_code=status)
    resp.delete_cookie(STATE_COOKIE, path="/")
    return resp


@router.get("/auth/oidc/callback")
def oidc_callback(
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
    p: OidcProvider = Depends(provider),
) -> Response:
    settings: Settings = request.app.state.settings
    db: Database = request.app.state.db
    if error:
        return _fail(400, "sign-in was cancelled or refused by the identity provider")
    try:
        saved = jwt.decode(
            request.cookies.get(STATE_COOKIE, ""),
            settings.secret_key,
            algorithms=["HS256"],
            audience=_STATE_AUD,
        )
    except jwt.InvalidTokenError:
        return _fail(400, "sign-in expired or was started elsewhere: try again")
    if not code or not secrets.compare_digest(state, str(saved["st"])):
        return _fail(400, "state mismatch")
    try:
        tokens = p.exchange(code, str(saved["v"]))
        claims = p.verify_id_token(str(tokens.get("id_token", "")), str(saved["n"]))
    except (OidcError, jwt.InvalidTokenError) as exc:
        return _fail(401, f"sign-in rejected: {exc}")
    email = str(claims.get("email", "")).strip().lower()
    if not email or claims.get("email_verified") is not True:
        return _fail(403, "the identity provider did not confirm your email address")
    superadmin = email in {e.strip().lower() for e in settings.sso_superadmin_emails}
    with db.session() as s:
        members = list(s.scalars(select(SsoMember).where(SsoMember.email == email)))
        for m in members:
            m.last_login_at = utcnow()
    if not members and not superadmin:
        return _fail(403, f"{email} is not a member of any organization")
    session = jwt.encode(
        {
            "aud": _SESSION_AUD,
            "sub": email,
            "sa": superadmin,
            "org": sorted(m.org_id for m in members)[0] if members else None,
            "iat": int(time.time()),
            "exp": int(time.time()) + settings.sso_session_ttl_s,
        },
        settings.secret_key,
        algorithm="HS256",
    )
    resp = RedirectResponse("/dashboard/", status_code=302)
    resp.delete_cookie(STATE_COOKIE, path="/")
    resp.set_cookie(
        SESSION_COOKIE,
        session,
        max_age=settings.sso_session_ttl_s,
        samesite="strict",
        **_cookie_kwargs(settings),
    )
    return resp


@router.post("/auth/logout")
def logout() -> Response:
    resp = Response(status_code=204)
    resp.delete_cookie(SESSION_COOKIE, path="/")
    return resp


def principal_from_cookie(request: Request, db: Session, settings: Settings) -> Principal | None:
    """The dashboard session, if the cookie and the CSRF header are both present and valid
    and the person is still a member (or a configured super-admin)."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token or request.headers.get(CSRF_HEADER) != "1":
        return None
    try:
        c = jwt.decode(token, settings.secret_key, algorithms=["HS256"], audience=_SESSION_AUD)
    except jwt.InvalidTokenError:
        return None
    email = str(c["sub"])
    if c.get("sa") and email in {e.strip().lower() for e in settings.sso_superadmin_emails}:
        return Principal(None, frozenset(), f"superadmin:sso:{email}")
    member = db.scalar(
        select(SsoMember).where(SsoMember.email == email, SsoMember.org_id == c.get("org"))
    )
    if member is None:  # removed since signing in
        return None
    return Principal(member.org_id, ROLE_SCOPES.get(member.role, frozenset()), f"sso:{email}")
