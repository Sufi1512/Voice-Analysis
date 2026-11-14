"""Envelope encryption for stored secrets (MFA seeds, provider keys).

Each secret gets its own random 256-bit data key (DEK). The value is encrypted with the DEK
(AES-256-GCM), and the DEK is wrapped by a key-encryption key (KEK) from settings; a KMS
adapter can replace the local KEK later without changing stored rows. Both layers carry
the secret's id (and the KEK id) as associated data, so a ciphertext copied onto another
row, or opened with another key, fails instead of decrypting.
"""

import os
from dataclasses import dataclass, field

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import BaseModel

KEY_BYTES = 32
NONCE_BYTES = 12


class SecretError(Exception):
    """A secret could not be opened (tampered, wrong key, or not this secret)."""


@dataclass(frozen=True)
class Kek:
    """A key-encryption key. Its bytes never appear in repr or str."""

    kek_id: str
    key: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if len(self.key) != KEY_BYTES:
            raise ValueError(f"key-encryption key must be {KEY_BYTES} bytes")


class SealedSecret(BaseModel):
    """What is stored: ciphertext and wrapped data key, never the plaintext."""

    ciphertext: bytes
    wrapped_dek: bytes
    kek_id: str


def _encrypt(key: bytes, plaintext: bytes, aad: bytes) -> bytes:
    nonce = os.urandom(NONCE_BYTES)
    return nonce + AESGCM(key).encrypt(nonce, plaintext, aad)


def _decrypt(key: bytes, blob: bytes, aad: bytes) -> bytes:
    try:
        return AESGCM(key).decrypt(blob[:NONCE_BYTES], blob[NONCE_BYTES:], aad)
    except (InvalidTag, ValueError) as exc:
        raise SecretError("secret could not be opened") from exc


def seal_secret(plaintext: bytes, kek: Kek, *, secret_id: str) -> SealedSecret:
    dek = AESGCM.generate_key(bit_length=KEY_BYTES * 8)
    aad = secret_id.encode()
    return SealedSecret(
        ciphertext=_encrypt(dek, plaintext, aad),
        wrapped_dek=_encrypt(kek.key, dek, aad + b"|" + kek.kek_id.encode()),
        kek_id=kek.kek_id,
    )


def open_secret(sealed: SealedSecret, keks: dict[str, Kek], *, secret_id: str) -> bytes:
    kek = keks.get(sealed.kek_id)
    if kek is None:
        raise SecretError(f"unknown key-encryption key {sealed.kek_id!r}")
    aad = secret_id.encode()
    dek = _decrypt(kek.key, sealed.wrapped_dek, aad + b"|" + kek.kek_id.encode())
    return _decrypt(dek, sealed.ciphertext, aad)
