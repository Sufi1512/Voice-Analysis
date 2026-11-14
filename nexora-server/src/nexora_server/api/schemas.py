"""Request and response models for the REST API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class OrgCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    max_concurrent_sessions: int = Field(10, ge=1, le=100_000)
    monthly_minutes_quota: int | None = Field(None, ge=0)
    relay_allowlist: list[str] = Field(
        default_factory=list,
        description="Hosts the relay may connect to, e.g. 'agent.example.com' or '*.example.com'.",
    )


class OrgUpdate(BaseModel):
    name: str | None = None
    active: bool | None = None
    max_concurrent_sessions: int | None = Field(None, ge=1, le=100_000)
    monthly_minutes_quota: int | None = Field(None, ge=0)
    relay_allowlist: list[str] | None = None
    stripe_customer_id: str | None = Field(None, pattern=r"^cus_[A-Za-z0-9]+$", max_length=64)


class OrgOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    active: bool
    max_concurrent_sessions: int
    monthly_minutes_quota: int | None
    relay_allowlist: list[str]
    stripe_customer_id: str | None = None
    created_at: datetime


class OrgCreated(BaseModel):
    organization: OrgOut
    api_key: str = Field(description="Initial admin key. Shown once: store it securely.")


class KeyCreate(BaseModel):
    name: str = Field("", max_length=200)
    scopes: list[Literal["stream", "admin", "usage:read"]] = Field(default=["stream"])
    org_id: str | None = None  # super-admin only


class KeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    org_id: str
    name: str
    prefix: str
    scopes: list[str]
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class KeyCreated(BaseModel):
    key: KeyOut
    api_key: str = Field(description="Shown once: store it securely.")


class ProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")
    audio_settings: dict[str, Any] = Field(
        default_factory=dict,
        description="Any nexora-audio NexoraConfig field except stream format.",
    )
    turn_settings: dict[str, Any] | None = Field(
        default_factory=dict, description="TurnConfig fields; null disables turn events."
    )
    is_default: bool = False
    org_id: str | None = None  # super-admin only


class ProfileUpdate(BaseModel):
    audio_settings: dict[str, Any] | None = None
    turn_settings: dict[str, Any] | None = None
    disable_turns: bool = False
    is_default: bool | None = None


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    org_id: str
    name: str
    audio_settings: dict[str, Any]
    turn_settings: dict[str, Any] | None
    is_default: bool
    created_at: datetime
    updated_at: datetime


class TokenRequest(BaseModel):
    mode: Literal["process", "relay"] = "process"
    profile: str | None = None
    relay_target: str | None = Field(None, description="Agent WebSocket URL (relay mode).")
    ttl_s: int | None = Field(None, ge=30, le=86400)


class TokenOut(BaseModel):
    token: str
    expires_at: int
    stream_url_path: str


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    org_id: str
    profile_id: str | None
    mode: str
    status: str
    input_format: dict[str, Any]
    backends: list[str]
    audio_seconds: float
    event_counts: dict[str, Any]
    p99_processing_ms: float | None
    quality: dict[str, Any] = {}
    close_code: int | None
    close_reason: str | None
    started_at: datetime
    ended_at: datetime | None


class UsageOut(BaseModel):
    org_id: str
    period_start: datetime
    period_end: datetime
    audio_minutes: float
    sessions: int
    monthly_minutes_quota: int | None
    month_to_date_minutes: float
    active_sessions: int = 0  # calls running now, on every server
    days: list[dict[str, Any]]


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    org_id: str | None
    actor: str
    action: str
    details: dict[str, Any]
    at: datetime


class MeOut(BaseModel):
    """Who the caller is (the dashboard's first request)."""

    actor: str
    superadmin: bool
    org_id: str | None
    org_name: str | None
    scopes: list[str]


class SsoMemberIn(BaseModel):
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    role: Literal["admin", "viewer"] = "admin"
    org_id: str | None = None  # super-admin only


class SsoMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    org_id: str
    email: str
    role: str
    created_at: datetime
    last_login_at: datetime | None


class UsageReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    org_id: str
    period_start: datetime
    period_end: datetime
    audio_seconds: float
    reported_seconds: int
    status: str
    error: str | None
    sent_at: datetime | None
