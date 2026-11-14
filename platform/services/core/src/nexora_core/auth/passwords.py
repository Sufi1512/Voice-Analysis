"""argon2id password hashing (argon2-cffi defaults: RFC 9106 low-memory profile)."""

from functools import cache

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


@cache
def _dummy_hash() -> str:
    return _hasher.hash("nexora-dummy-password-for-timing")


def verify_password(password_hash: str | None, password: str) -> bool:
    """Constant-shape check: with no stored hash, still spend one argon2 verification."""
    try:
        return _hasher.verify(password_hash or _dummy_hash(), password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)
