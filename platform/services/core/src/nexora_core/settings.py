"""Service settings, read from ``NEXORA_*`` environment variables."""

import base64
import binascii
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from nexora_core.secrets import KEY_BYTES, Kek

MIN_SECRET_LENGTH = 32


class Settings(BaseSettings):
    """NEXORA Core configuration. Production refuses to start with unsafe values."""

    model_config = SettingsConfigDict(env_prefix="NEXORA_", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "postgresql+asyncpg://nexora:nexora@localhost:5432/nexora"
    session_secret: SecretStr = Field(default=SecretStr(""))
    #: Public sign-up. Off: accounts exist only by invitation (enterprise first).
    self_signup: bool = False
    log_level: str = "INFO"
    #: Key-encryption key for stored secrets: base64 of 32 random bytes. Required in production.
    kek: SecretStr = Field(default=SecretStr(""))
    kek_id: str = "local-1"

    @field_validator("kek")
    @classmethod
    def _kek_is_32_bytes(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        if raw:
            try:
                decoded = base64.b64decode(raw, validate=True)
            except binascii.Error as exc:
                raise ValueError("kek must be base64") from exc
            if len(decoded) != KEY_BYTES:
                raise ValueError(f"kek must decode to {KEY_BYTES} bytes")
        return value

    def kek_ring(self) -> dict[str, Kek]:
        """The key-encryption keys this service can open secrets with."""
        raw = self.kek.get_secret_value()
        return {self.kek_id: Kek(kek_id=self.kek_id, key=base64.b64decode(raw))} if raw else {}

    @model_validator(mode="after")
    def _production_is_safe(self) -> "Settings":
        if (
            self.environment == "production"
            and len(self.session_secret.get_secret_value()) < MIN_SECRET_LENGTH
        ):
            raise ValueError(f"session_secret must be at least {MIN_SECRET_LENGTH} characters in production")
        if self.environment == "production" and not self.kek.get_secret_value():
            raise ValueError("kek is required in production")
        return self
