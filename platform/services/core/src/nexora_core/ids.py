"""Opaque, prefixed identifiers: ``org_3f9c…`` (80 random bits, hex)."""

import secrets


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(10)}"
