"""API keys and short-lived session tokens."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

import jwt

SCOPES = ("stream", "admin", "usage:read")
KEY_PREFIX = "nx_"
_TOKEN_AUDIENCE = "nexora-stream"


@dataclass(frozen=True)
class NewKey:
    plaintext: str  # shown to the customer once, never stored
    prefix: str
    key_hash: str


def hash_key(plaintext: str, pepper: str) -> str:
    return hmac.new(pepper.encode(), plaintext.encode(), hashlib.sha256).hexdigest()


def generate_api_key(pepper: str) -> NewKey:
    """``nx_<12-char id>_<43-char secret>`` (256-bit secret)."""
    ident = secrets.token_hex(6)
    plaintext = f"{KEY_PREFIX}{ident}_{secrets.token_urlsafe(32)}"
    return NewKey(plaintext, f"{KEY_PREFIX}{ident}", hash_key(plaintext, pepper))


def key_prefix(plaintext: str) -> str | None:
    if not plaintext.startswith(KEY_PREFIX):
        return None
    parts = plaintext.split("_", 2)
    if len(parts) != 3 or len(parts[1]) != 12:
        return None
    return f"{KEY_PREFIX}{parts[1]}"


def verify_key(plaintext: str, stored_hash: str, pepper: str) -> bool:
    return hmac.compare_digest(hash_key(plaintext, pepper), stored_hash)


@dataclass(frozen=True)
class Principal:
    """Who is calling: a super-admin, or an organization via an API key or session token."""

    org_id: str | None
    scopes: frozenset[str]
    actor: str  # "superadmin", "key:<id>" or "token:<jti>"
    api_key_id: str | None = None
    token_claims: dict[str, Any] = field(default_factory=dict)

    @property
    def is_superadmin(self) -> bool:
        return self.actor == "superadmin" or self.actor.startswith("superadmin:")

    def has(self, scope: str) -> bool:
        return self.is_superadmin or scope in self.scopes


def mint_session_token(
    secret: str,
    *,
    org_id: str,
    ttl_s: int,
    mode: str,
    profile_id: str | None,
    relay_target: str | None = None,
    api_key_id: str | None = None,
) -> tuple[str, int]:
    now = int(time.time())
    exp = now + ttl_s
    claims = {
        "aud": _TOKEN_AUDIENCE,
        "sub": org_id,
        "iat": now,
        "exp": exp,
        "jti": secrets.token_hex(8),
        "mode": mode,
        "profile_id": profile_id,
        "relay_target": relay_target,
        "kid": api_key_id,
    }
    return jwt.encode(claims, secret, algorithm="HS256"), exp


def decode_session_token(secret: str, token: str) -> dict[str, Any]:
    """Raises ``jwt.InvalidTokenError`` if invalid or expired."""
    claims: dict[str, Any] = jwt.decode(
        token, secret, algorithms=["HS256"], audience=_TOKEN_AUDIENCE
    )
    return claims
