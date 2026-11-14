"""Service settings, read from ``NEXORA_*`` environment variables."""

from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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

    @model_validator(mode="after")
    def _production_is_safe(self) -> "Settings":
        if (
            self.environment == "production"
            and len(self.session_secret.get_secret_value()) < MIN_SECRET_LENGTH
        ):
            raise ValueError(f"session_secret must be at least {MIN_SECRET_LENGTH} characters in production")
        return self
