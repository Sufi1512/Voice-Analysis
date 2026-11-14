"""Database migrations (Alembic), run in code or with ``nexora-server migrate``."""

from __future__ import annotations

import logging

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

log = logging.getLogger("nexora.migrate")
FIRST_REVISION = "0001"


def config(url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", "nexora_server:migrations")
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


def upgrade(url: str, revision: str = "head") -> None:
    """Bring the database to ``revision``. A database made by the old ``create_all`` (tables
    but no ``alembic_version``) is stamped as the first revision first, not recreated."""
    cfg = config(url)
    engine = create_engine(url)
    try:
        tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
    if "organizations" in tables and "alembic_version" not in tables:
        log.info("existing database without migration history: stamping %s", FIRST_REVISION)
        command.stamp(cfg, FIRST_REVISION)
    command.upgrade(cfg, revision)


def downgrade(url: str, revision: str) -> None:
    command.downgrade(config(url), revision)
