"""Shared fixtures: a throwaway PostgreSQL database per test session.

Set NEXORA_TEST_ADMIN_URL to a superuser connection (CI uses the PostgreSQL service;
locally the default below). Each session creates its own database and drops it after.
"""

import os
import secrets
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

ADMIN_URL = os.environ.get(
    "NEXORA_TEST_ADMIN_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/postgres"
)


@pytest.fixture(scope="session")
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
