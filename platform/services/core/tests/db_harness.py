"""Helpers to create the two database roles and run migrations in tests."""

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from nexora_core.db.migrate import downgrade, upgrade

APP_ROLE, ADMIN_ROLE, ROLE_PASSWORD = "nexora_app", "nexora_admin", "test-only-password"


async def ensure_roles(admin_url: str) -> None:
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        for role, extra in ((APP_ROLE, ""), (ADMIN_ROLE, " BYPASSRLS")):
            exists = await conn.scalar(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": role})
            if not exists:
                await conn.execute(text(f"CREATE ROLE {role} LOGIN PASSWORD '{ROLE_PASSWORD}'{extra}"))
    await engine.dispose()


def as_role(database_url: str, role: str) -> str:
    return (
        make_url(database_url)
        .set(username=role, password=ROLE_PASSWORD)
        .render_as_string(hide_password=False)
    )


def app_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(as_role(database_url, APP_ROLE))


__all__ = ["ADMIN_ROLE", "APP_ROLE", "app_engine", "as_role", "downgrade", "ensure_roles", "upgrade"]
