"""Failed sign-in counting: N failures inside one minute lock the key for 15 minutes."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

WINDOW = timedelta(minutes=1)
LOCK = timedelta(minutes=15)


@dataclass(frozen=True)
class Limit:
    prefix: str
    max_failures: int


EMAIL = Limit("email", 10)
IP = Limit("ip", 100)  # many users behind one office NAT; the email limit is the real guard


def key(limit: Limit, value: str) -> str:
    return f"{limit.prefix}:{value.strip().lower()}"


async def locked_until(conn: AsyncConnection, keys: list[str], *, now: datetime) -> datetime | None:
    return await conn.scalar(
        text("SELECT max(locked_until) FROM login_throttle WHERE key = ANY(:k) AND locked_until > :now"),
        {"k": keys, "now": now},
    )


async def record_failure(conn: AsyncConnection, k: str, limit: Limit, *, now: datetime) -> None:
    """Atomic: concurrent failures for one key never lose a count."""
    failures = await conn.scalar(
        text(
            "INSERT INTO login_throttle AS t (key, window_started_at, failures) VALUES (:k, :now, 1)"
            " ON CONFLICT (key) DO UPDATE SET"
            " failures = CASE WHEN t.window_started_at <= :start THEN 1 ELSE t.failures + 1 END,"
            " window_started_at = CASE WHEN t.window_started_at <= :start THEN :now"
            " ELSE t.window_started_at END"
            " RETURNING failures"
        ),
        {"k": k, "now": now, "start": now - WINDOW},
    )
    if failures is not None and failures >= limit.max_failures:
        await conn.execute(
            text("UPDATE login_throttle SET locked_until = :until, failures = 0 WHERE key = :k"),
            {"k": k, "until": now + LOCK},
        )


async def clear(conn: AsyncConnection, k: str) -> None:
    await conn.execute(text("DELETE FROM login_throttle WHERE key = :k"), {"k": k})
