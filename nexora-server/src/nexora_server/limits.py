"""Organization concurrency limits: per instance, or cluster-wide with Redis leases.

With ``NEXORA_REDIS_URL`` every open session holds a lease in a Redis sorted set per
organization (member = lease id, score = expiry on the Redis clock). One Lua script drops
expired leases, checks the count and adds the lease atomically, so the limit holds across
all instances. Leases are renewed while the session runs and expire if an instance dies.
If Redis cannot be reached the limiter falls back to counting on this instance only.
"""

from __future__ import annotations

import logging
import secrets
import threading
from collections import defaultdict
from typing import Any, Protocol

log = logging.getLogger("nexora.limits")

# KEYS[1] leases key; ARGV: ttl_ms, limit, lease id. Returns 1 if the lease was taken.
_ACQUIRE = """
local t = redis.call('TIME')
local now = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now)
if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[2]) then
  return 0
end
redis.call('ZADD', KEYS[1], now + tonumber(ARGV[1]), ARGV[3])
redis.call('PEXPIRE', KEYS[1], tonumber(ARGV[1]) * 2)
return 1
"""

# KEYS[1] leases key; ARGV: ttl_ms, lease id. Renews (or re-adds) the lease.
_RENEW = """
local t = redis.call('TIME')
local now = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
redis.call('ZADD', KEYS[1], now + tonumber(ARGV[1]), ARGV[2])
redis.call('PEXPIRE', KEYS[1], tonumber(ARGV[1]) * 2)
return 1
"""


class OrgLimiter(Protocol):
    async def acquire(self, org_id: str, limit: int) -> str | None:
        """Take a slot; returns a lease id, or None if the organization is at its limit."""

    async def renew(self, org_id: str, lease: str) -> None: ...

    async def release(self, org_id: str, lease: str) -> None: ...

    def active_for(self, org_id: str) -> int:
        """Sessions this instance holds for the organization."""


class LocalOrgLimiter:
    """Counts on this instance only (single instance, development, tests)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._leases: dict[str, set[str]] = defaultdict(set)

    def try_take(self, org_id: str, limit: int) -> str | None:
        with self._lock:
            if len(self._leases[org_id]) >= limit:
                return None
            lease = "local_" + secrets.token_hex(8)
            self._leases[org_id].add(lease)
            return lease

    def drop(self, org_id: str, lease: str) -> None:
        with self._lock:
            self._leases[org_id].discard(lease)
            if not self._leases[org_id]:
                del self._leases[org_id]

    async def acquire(self, org_id: str, limit: int) -> str | None:
        return self.try_take(org_id, limit)

    async def renew(self, org_id: str, lease: str) -> None:
        return None

    async def release(self, org_id: str, lease: str) -> None:
        self.drop(org_id, lease)

    def active_for(self, org_id: str) -> int:
        with self._lock:
            return len(self._leases.get(org_id, ()))


class RedisOrgLimiter:
    """Cluster-wide limits with Redis leases; falls back to local counting on Redis errors."""

    def __init__(
        self,
        client: Any,
        ttl_s: float = 30.0,
        prefix: str = "nexora:",
        on_error: Any = None,
    ) -> None:
        self.client = client  # a redis.asyncio.Redis
        self.ttl_ms = int(ttl_s * 1000)
        self.prefix = prefix
        self.local = LocalOrgLimiter()  # this instance's own leases, and the fallback
        self._on_error = on_error
        self._acquire = client.register_script(_ACQUIRE)
        self._renew = client.register_script(_RENEW)

    @classmethod
    def from_url(cls, url: str, **kwargs: Any) -> RedisOrgLimiter:
        import redis.asyncio as aioredis

        return cls(aioredis.from_url(url, socket_timeout=2.0, socket_connect_timeout=2.0), **kwargs)

    def key(self, org_id: str) -> str:
        return f"{self.prefix}org:{org_id}:leases"

    def _failed(self, what: str, exc: Exception) -> None:
        log.warning("redis %s failed, using this instance's count: %s", what, exc)
        if self._on_error is not None:
            self._on_error()

    async def acquire(self, org_id: str, limit: int) -> str | None:
        lease = "lease_" + secrets.token_hex(10)
        try:
            ok = await self._acquire(keys=[self.key(org_id)], args=[self.ttl_ms, limit, lease])
        except Exception as exc:
            self._failed("acquire", exc)
            return self.local.try_take(org_id, limit)
        if not int(ok):
            return None
        with self.local._lock:
            self.local._leases[org_id].add(lease)
        return lease

    async def renew(self, org_id: str, lease: str) -> None:
        if lease.startswith("local_"):
            return
        try:
            await self._renew(keys=[self.key(org_id)], args=[self.ttl_ms, lease])
        except Exception as exc:
            self._failed("renew", exc)

    async def release(self, org_id: str, lease: str) -> None:
        self.local.drop(org_id, lease)
        if lease.startswith("local_"):
            return
        try:
            await self.client.zrem(self.key(org_id), lease)
        except Exception as exc:  # the lease expires by itself
            self._failed("release", exc)

    def active_for(self, org_id: str) -> int:
        return self.local.active_for(org_id)

    async def cluster_count(self, org_id: str) -> int:
        """Live leases for the organization across all instances."""
        t = await self.client.time()
        now = int(t[0]) * 1000 + int(t[1]) // 1000
        return int(await self.client.zcount(self.key(org_id), now, "+inf"))
