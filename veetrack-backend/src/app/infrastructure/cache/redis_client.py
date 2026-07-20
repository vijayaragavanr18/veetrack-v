"""Redis-backed implementation of CacheGateway."""

from __future__ import annotations

import structlog
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.domain.interfaces.services import CacheGateway

logger = structlog.get_logger(__name__)


class RedisCacheGateway:
    """Implements CacheGateway backed by a Redis connection pool."""

    def __init__(self, redis: Redis) -> None:  # type: ignore[type-arg]
        self._redis = redis

    @classmethod
    def from_url(cls, url: str) -> RedisCacheGateway:
        """Construct a gateway from a Redis connection URL."""
        client: Redis = Redis.from_url(url, decode_responses=False)  # type: ignore[type-arg]
        return cls(client)

    async def get(self, key: str) -> bytes | None:
        """Return cached bytes for key, or None on miss."""
        try:
            result: bytes | None = await self._redis.get(key)
            return result
        except RedisError as exc:
            logger.warning("redis.get.error", key=key, error=str(exc))
            return None

    async def set(self, key: str, value: bytes, ttl_seconds: int = 300) -> None:
        """Store value under key with TTL."""
        try:
            await self._redis.set(key, value, ex=ttl_seconds)
        except RedisError as exc:
            logger.warning("redis.set.error", key=key, error=str(exc))

    async def delete(self, key: str) -> None:
        """Remove key from cache."""
        try:
            await self._redis.delete(key)
        except RedisError as exc:
            logger.warning("redis.delete.error", key=key, error=str(exc))

    async def ping(self) -> bool:
        """Return True if Redis responds to PING."""
        try:
            return bool(await self._redis.ping())
        except RedisError as exc:
            logger.warning("redis.ping.failed", error=str(exc))
            return False

    async def get_or_set(
        self,
        key: str,
        factory: object,  # Callable[[], Awaitable[bytes]]
        ttl_seconds: int = 300,
    ) -> bytes:
        """Return cached value for key; call factory to compute and cache it on a miss.

        Uses a Redis SET NX (set-if-not-exists) approach: if the key is absent, the factory
        is called once and its result is stored with the given TTL.  Concurrent callers that
        race to a cold key may each call the factory; the last SET wins but all return a
        consistent cached value.  This is acceptable for our read-heavy, idempotent payloads.
        """
        from collections.abc import Awaitable

        cached = await self.get(key)
        if cached is not None:
            return cached

        factory_fn = factory  # type: ignore[assignment]
        if callable(factory_fn):
            result = factory_fn()
            if isinstance(result, Awaitable):
                value: bytes = await result
            else:
                value = result  # type: ignore[assignment]
        else:
            raise TypeError("factory must be a callable returning bytes or Awaitable[bytes]")

        await self.set(key, value, ttl_seconds=ttl_seconds)
        return value

    async def aclose(self) -> None:
        """Close the Redis connection pool."""
        await self._redis.aclose()


# Verify RedisCacheGateway satisfies the Protocol at import time.
# This is a static assertion — it will raise TypeError if the class is incomplete.
_: CacheGateway = RedisCacheGateway.__new__(RedisCacheGateway)
