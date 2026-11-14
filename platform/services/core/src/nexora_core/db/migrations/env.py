"""Alembic environment: async engine, URL handed in by ``nexora_core.db.migrate``."""

import asyncio

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine


def _run(connection) -> None:
    context.configure(connection=connection, target_metadata=None, transaction_per_migration=True)
    with context.begin_transaction():
        context.run_migrations()


async def _main() -> None:
    engine = create_async_engine(context.config.attributes["database_url"])
    async with engine.connect() as conn:
        await conn.run_sync(_run)
        await conn.commit()
    await engine.dispose()


asyncio.run(_main())
