"""Server configuration from environment variables (prefix ``NEXORA_``)."""

from __future__ import annotations

import logging
import os
import secrets
from typing import Literal

from pydantic import BaseModel, Field, model_validator

log = logging.getLogger("nexora.settings")


def _default_capacity() -> int:
    # measured in E10 (docs/E10_RESULTS.md): about 2 real-time calls per core with the
    # full default pipeline (noise removal, guards, VAD, Smart Turn) in one process
    return 2 * (os.cpu_count() or 1)


class Settings(BaseModel):
    """All settings can be overridden with ``NEXORA_<NAME>`` environment variables."""

    database_url: str = "sqlite:///./nexora.db"
    secret_key: str = Field(
        default="", description="Signs session tokens and peppers API-key hashes. Required in prod."
    )
    admin_api_key: str = Field(default="", description="Super-admin bootstrap key (env only).")
    deployment_mode: Literal["saas", "self_hosted"] = "saas"
    max_sessions: int = Field(default_factory=_default_capacity, ge=1)
    worker_threads: int = Field(default_factory=lambda: os.cpu_count() or 1, ge=1)
    session_token_ttl_s: int = Field(300, ge=30, le=86400)
    max_message_bytes: int = Field(256 * 1024, ge=1024)
    idle_timeout_s: float = Field(30.0, gt=0)
    quota_check_interval_s: float = Field(60.0, gt=0)
    agent_silence_ms: float = Field(300.0, gt=0)
    redis_url: str = Field(
        default="", description="Redis for cluster-wide organization limits (empty: per instance)."
    )
    lease_ttl_s: float = Field(30.0, ge=3, description="Session lease lifetime in Redis.")
    drain_timeout_s: float = Field(
        600.0, ge=0, description="On SIGTERM, wait this long for open sessions to finish."
    )
    checkpoint_interval_s: float = Field(
        30.0, gt=0, description="Save each running call's audio seconds and heartbeat this often."
    )
    stale_session_after_s: float = Field(
        120.0,
        gt=0,
        description="A call with no heartbeat for this long is closed as lost (server died).",
    )
    # new WebSocket connections per client IP (token bucket); 0 turns the limit off
    connect_rate_per_ip: float = Field(20.0, ge=0, description="Sustained connections/s per IP.")
    connect_burst_per_ip: int = Field(100, ge=1, description="Connections allowed in a burst.")
    forwarded_allow_ips: str = Field(
        "127.0.0.1",
        description="Proxies whose X-Forwarded-For is trusted for the client IP ('*': all; "
        "only when nothing but the load balancer can reach the server).",
    )
    auto_migrate: bool = Field(
        True, description="Run database migrations at start-up (false: an init container does)."
    )
    # single sign-on for the dashboard (OpenID Connect); empty issuer: off
    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_redirect_url: str = Field(
        default="", description="https://<host>/auth/oidc/callback, as registered at the IdP."
    )
    sso_superadmin_emails: list[str] = Field(default_factory=list)
    sso_session_ttl_s: int = Field(8 * 3600, ge=300, le=7 * 86400)
    cookie_secure: bool = Field(True, description="Send cookies over HTTPS only.")
    # metered billing (Stripe billing meters); empty key: off
    stripe_api_key: str = ""
    stripe_meter_event: str = "nexora_audio_seconds"
    billing_interval_s: float = Field(300.0, ge=10)
    log_level: str = "INFO"
    cors_origins: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _stale_after_checkpoints(self) -> Settings:
        if self.stale_session_after_s < 2 * self.checkpoint_interval_s:
            raise ValueError("stale_session_after_s must be at least 2x checkpoint_interval_s")
        return self

    @classmethod
    def from_env(cls, **overrides: object) -> Settings:
        data: dict[str, object] = {}
        for name, field in cls.model_fields.items():
            raw = os.environ.get(f"NEXORA_{name.upper()}")
            if raw is None:
                continue
            ann = field.annotation
            if ann is int:
                data[name] = int(raw)
            elif ann is float:
                data[name] = float(raw)
            elif ann is bool:
                data[name] = raw.strip().lower() in ("1", "true", "yes", "on")
            elif name in ("cors_origins", "sso_superadmin_emails"):
                data[name] = [o.strip() for o in raw.split(",") if o.strip()]
            else:
                data[name] = raw
        data.update(overrides)
        settings = cls.model_validate(data)
        if not settings.secret_key:
            settings.secret_key = secrets.token_urlsafe(48)
            log.warning(
                "NEXORA_SECRET_KEY not set: using a random key. Session tokens and API keys "
                "will not survive a restart or work across instances. Set it in production."
            )
        return settings
