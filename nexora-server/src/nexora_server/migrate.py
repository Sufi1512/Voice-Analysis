"""Database migrations (Alembic), run in code or with ``nexora-server migrate``."""

from __future__ import annotations

import logging

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

log = logging.getLogger("nexora.migrate")
FIRST_REVISION = "0001"
# for databases made by create_all (no migration history): a table that only exists from
# a given revision on tells which revision the database already matches
MARKERS = [("usage_reports", "0002"), ("organizations", FIRST_REVISION)]


def config(url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", "nexora_server:migrations")
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


def upgrade(url: str, revision: str = "head") -> None:
    """Bring the database to ``revision``. A database made by ``create_all`` (tables but no
    ``alembic_version``) is stamped with the revision it matches first, not recreated."""
    cfg = config(url)
    engine = create_engine(url)
    try:
        tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
    if "alembic_version" not in tables:
        found = next((rev for table, rev in MARKERS if table in tables), None)
        if found is not None:
            log.info("existing database without migration history: stamping %s", found)
            command.stamp(cfg, found)
    command.upgrade(cfg, revision)


def downgrade(url: str, revision: str) -> None:
    command.downgrade(config(url), revision)
