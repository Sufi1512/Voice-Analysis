"""Shared fixtures: a throwaway PostgreSQL database per test session.

Set NEXORA_TEST_ADMIN_URL to a superuser connection (CI uses the PostgreSQL service;
locally the default below). Each test module gets its own database, dropped after the module.
"""

import os
import secrets
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.db_harness import ensure_roles, upgrade

ADMIN_URL = os.environ.get(
    "NEXORA_TEST_ADMIN_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/postgres"
)


@pytest.fixture(scope="module")
async def database_url() -> AsyncIterator[str]:
    name = f"nexora_test_{secrets.token_hex(4)}"
    admin = create_async_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        await conn.execute(text(f'CREATE DATABASE "{name}"'))
    base, _, _ = ADMIN_URL.rpartition("/")
    yield f"{base}/{name}"
    async with admin.connect() as conn:
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    await admin.dispose()


@pytest.fixture(scope="module")
async def migrated(database_url: str) -> str:
    """The module's database with all migrations applied and the two service roles present."""
    await ensure_roles(ADMIN_URL)
    await upgrade(database_url)
    return database_url
