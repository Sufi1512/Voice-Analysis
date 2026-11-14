"""C3: envelope encryption for secrets (MFA seeds, provider keys)."""

import base64

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from nexora_core.secrets import Kek, SecretError, open_secret, seal_secret
from nexora_core.settings import Settings

KEK = Kek(kek_id="local-1", key=bytes(range(32)))
OTHER = Kek(kek_id="local-2", key=bytes(reversed(range(32))))


@given(plaintext=st.binary(max_size=4096), secret_id=st.text(min_size=1, max_size=40))
def test_round_trip(plaintext, secret_id):
    sealed = seal_secret(plaintext, KEK, secret_id=secret_id)
    assert open_secret(sealed, {KEK.kek_id: KEK}, secret_id=secret_id) == plaintext


def test_ciphertext_does_not_contain_plaintext():
    sealed = seal_secret(b"JBSWY3DPEHPK3PXP", KEK, secret_id="sec_1")
    assert b"JBSWY3DPEHPK3PXP" not in sealed.ciphertext + sealed.wrapped_dek


def test_same_plaintext_seals_differently():
    a, b = (seal_secret(b"same", KEK, secret_id="sec_1") for _ in range(2))
    assert a.ciphertext != b.ciphertext


def test_tampered_ciphertext_refused():
    sealed = seal_secret(b"value", KEK, secret_id="sec_1")
    broken = sealed.model_copy(
        update={"ciphertext": sealed.ciphertext[:-1] + bytes([sealed.ciphertext[-1] ^ 1])}
    )
    with pytest.raises(SecretError):
        open_secret(broken, {KEK.kek_id: KEK}, secret_id="sec_1")


def test_wrong_kek_refused():
    sealed = seal_secret(b"value", KEK, secret_id="sec_1")
    with pytest.raises(SecretError):
        open_secret(
            sealed.model_copy(update={"kek_id": OTHER.kek_id}), {OTHER.kek_id: OTHER}, secret_id="sec_1"
        )


def test_unknown_kek_refused():
    sealed = seal_secret(b"value", KEK, secret_id="sec_1")
    with pytest.raises(SecretError, match="unknown key"):
        open_secret(sealed, {}, secret_id="sec_1")


def test_bound_to_its_secret_id():
    sealed = seal_secret(b"value", KEK, secret_id="sec_1")
    with pytest.raises(SecretError):
        open_secret(sealed, {KEK.kek_id: KEK}, secret_id="sec_2")


def test_kek_never_shown():
    assert "0001020304" not in repr(KEK)
    assert bytes(range(32)).hex() not in repr(KEK) + str(KEK)


def test_production_requires_kek():
    with pytest.raises(ValidationError, match="kek"):
        Settings(
            environment="production", database_url="postgresql+asyncpg://x:x@db/x", session_secret="s" * 40
        )


def test_settings_parse_kek():
    raw = base64.b64encode(bytes(range(32))).decode()
    s = Settings(environment="test", kek=raw, kek_id="k1")
    assert s.kek_ring() == {"k1": Kek(kek_id="k1", key=bytes(range(32)))}


def test_settings_reject_short_kek():
    with pytest.raises(ValidationError, match="32 bytes"):
        Settings(environment="test", kek=base64.b64encode(b"short").decode())
