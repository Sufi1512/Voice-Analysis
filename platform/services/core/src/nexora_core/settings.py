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
    #: Outgoing email (plain SMTP, set at deploy time; Mailpit locally).
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_security: Literal["none", "starttls", "tls"] = "none"
    smtp_username: str = ""
    smtp_password: SecretStr = Field(default=SecretStr(""))
    smtp_from: str = "NEXORA <no-reply@localhost>"
    #: Base URL of the portal, for links in emails.
    public_url: str = "https://localhost:3000"
    #: First platform owner, created on first start with a single-use set-password token.
    bootstrap_owner_email: str = ""
    #: Where that token is written (mode 0600). Mount a private volume here in production.
    bootstrap_token_file: str = ".nexora/bootstrap-owner-token"  # noqa: S105 - a path, not a secret

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
        if self.environment == "production" and self.smtp_security == "none":
            raise ValueError("smtp_security must be starttls or tls in production")
        return self
