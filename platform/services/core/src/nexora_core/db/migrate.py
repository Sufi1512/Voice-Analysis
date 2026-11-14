"""Run Alembic migrations programmatically (tests, the ``nexora-core migrate`` command)."""

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config

MIGRATIONS = Path(__file__).parent / "migrations"


def _config(database_url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.attributes["database_url"] = database_url
    return cfg


async def upgrade(database_url: str, revision: str = "head") -> None:
    await asyncio.to_thread(command.upgrade, _config(database_url), revision)


async def downgrade(database_url: str, revision: str = "base") -> None:
    await asyncio.to_thread(command.downgrade, _config(database_url), revision)
