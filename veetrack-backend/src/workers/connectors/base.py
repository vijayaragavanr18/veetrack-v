"""Redis-backed distributed token-bucket rate limiter + circuit breaker.

Identical semantics to apps/api/app/infrastructure/connectors/base.py —
kept separate to avoid cross-package coupling between the API and workers.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

import structlog
from redis.asyncio import Redis

logger = structlog.get_logger(__name__)

CIRCUIT_FAILURE_THRESHOLD = 5
CIRCUIT_RESET_SECONDS = 120

_BUCKET_PREFIX = "vt:ratelimit:"
_FAILURES_PREFIX = "vt:cb:failures:"
_OPEN_UNTIL_PREFIX = "vt:cb:open_until:"


class RateLimitExceeded(Exception):
    pass


class CircuitOpen(Exception):
    pass


class RedisRateLimiter:
    def __init__(
        self,
        redis: Redis,  # type: ignore[type-arg]
        source_id: str,
        calls_per_minute: int,
        *,
        failure_threshold: int = CIRCUIT_FAILURE_THRESHOLD,
        reset_seconds: int = CIRCUIT_RESET_SECONDS,
    ) -> None:
        self._redis = redis
        self._source_id = source_id
        self._calls_per_minute = calls_per_minute
        self._failure_threshold = failure_threshold
        self._reset_seconds = reset_seconds

    async def acquire(self) -> None:
        await self._check_circuit()
        await self._check_bucket()

    async def record_success(self) -> None:
        await self._redis.delete(self._failures_key())

    async def record_failure(self) -> None:
        failures_key = self._failures_key()
        count = await self._redis.incr(failures_key)
        await self._redis.expire(failures_key, self._reset_seconds * 2)
        if count >= self._failure_threshold:
            open_until = time.time() + self._reset_seconds
            await self._redis.set(self._open_until_key(), str(open_until))
            await self._redis.delete(failures_key)
            logger.warning(
                "connector.circuit_opened",
                source_id=self._source_id,
                open_until=datetime.fromtimestamp(open_until, tz=UTC).isoformat(),
            )

    async def is_circuit_open(self) -> bool:
        val = await self._redis.get(self._open_until_key())
        if val is None:
            return False
        return time.time() < float(val)

    async def circuit_open_until(self) -> datetime | None:
        val = await self._redis.get(self._open_until_key())
        if val is None:
            return None
        ts = float(val)
        if time.time() >= ts:
            await self._redis.delete(self._open_until_key())
            return None
        return datetime.fromtimestamp(ts, tz=UTC)

    async def calls_this_window(self) -> int:
        val = await self._redis.get(self._bucket_key())
        return int(val) if val else 0

    async def _check_circuit(self) -> None:
        val = await self._redis.get(self._open_until_key())
        if val is None:
            return
        open_until = float(val)
        if time.time() < open_until:
            raise CircuitOpen(
                f"Source {self._source_id!r}: circuit open until "
                f"{datetime.fromtimestamp(open_until, tz=UTC).isoformat()}"
            )
        await self._redis.delete(self._open_until_key())

    async def _check_bucket(self) -> None:
        bucket_key = self._bucket_key()
        count = await self._redis.incr(bucket_key)
        if count == 1:
            await self._redis.expire(bucket_key, 60)
        if count > self._calls_per_minute:
            raise RateLimitExceeded(
                f"Source {self._source_id!r}: rate limit of "
                f"{self._calls_per_minute} calls/min exhausted"
            )

    def _bucket_key(self) -> str:
        minute = datetime.now(UTC).strftime("%Y%m%dT%H%M")
        return f"{_BUCKET_PREFIX}{self._source_id}:{minute}"

    def _failures_key(self) -> str:
        return f"{_FAILURES_PREFIX}{self._source_id}"

    def _open_until_key(self) -> str:
        return f"{_OPEN_UNTIL_PREFIX}{self._source_id}"
