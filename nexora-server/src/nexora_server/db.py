"""Database models (SQLAlchemy 2). PostgreSQL in production, SQLite for dev and tests."""

from __future__ import annotations

import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, ClassVar

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    create_engine,
    event,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(10)}"


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    type_annotation_map: ClassVar[dict[Any, Any]] = {dict[str, Any]: JSON, list[str]: JSON}


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("org"))
    name: Mapped[str] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    max_concurrent_sessions: Mapped[int] = mapped_column(Integer, default=10)
    monthly_minutes_quota: Mapped[int | None] = mapped_column(Integer, nullable=True)
    relay_allowlist: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ApiKey(Base):
    __tablename__ = "api_keys"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("key"))
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    prefix: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    key_hash: Mapped[str] = mapped_column(String(128))
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Profile(Base):
    __tablename__ = "profiles"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("prf"))
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    audio_settings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    turn_settings: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, default=dict)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class SessionRecord(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("ses"))
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    profile_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    api_key_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    mode: Mapped[str] = mapped_column(String(16))  # process | relay
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | ended | failed
    input_format: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    backends: Mapped[list[str]] = mapped_column(JSON, default=list)
    audio_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    event_counts: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    p99_processing_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    close_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    close_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("aud"))
    org_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Database:
    def __init__(self, url: str) -> None:
        kwargs: dict[str, Any] = {"pool_pre_ping": True}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
        self.engine: Engine = create_engine(url, **kwargs)
        if url.startswith("sqlite"):

            @event.listens_for(self.engine, "connect")
            def _fk_on(dbapi_conn: Any, _: Any) -> None:
                dbapi_conn.execute("PRAGMA foreign_keys=ON")

        self._factory = sessionmaker(self.engine, expire_on_commit=False)

    def create_all(self) -> None:
        Base.metadata.create_all(self.engine)

    @contextmanager
    def session(self) -> Iterator[Session]:
        s = self._factory()
        try:
            yield s
            s.commit()
        except BaseException:
            s.rollback()
            raise
        finally:
            s.close()

    def ping(self) -> bool:
        from sqlalchemy import text

        with self.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
