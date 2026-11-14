"""Single-use bearer tokens (invitations, password set/reset): 256 bits, only SHA-256 stored."""

import hashlib
import secrets


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def new_token() -> tuple[str, str]:
    """Return (raw token for the recipient, hash to store)."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw)
