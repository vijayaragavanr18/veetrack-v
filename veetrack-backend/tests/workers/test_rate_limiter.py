"""Unit tests: workers RedisRateLimiter — token bucket and circuit breaker."""

from __future__ import annotations

import time

import fakeredis.aioredis as fakeredis
import pytest

from workers.connectors.base import CircuitOpen, RateLimitExceeded, RedisRateLimiter


@pytest.fixture()
async def redis() -> fakeredis.FakeRedis:
    return fakeredis.FakeRedis(decode_responses=False)


@pytest.fixture()
def limiter(redis: fakeredis.FakeRedis) -> RedisRateLimiter:
    return RedisRateLimiter(redis, source_id="test-src", calls_per_minute=3)


@pytest.mark.asyncio
async def test_allows_calls_within_quota(limiter: RedisRateLimiter) -> None:
    await limiter.acquire()
    await limiter.acquire()
    await limiter.acquire()


@pytest.mark.asyncio
async def test_blocks_nth_plus_one_call(limiter: RedisRateLimiter) -> None:
    for _ in range(3):
        await limiter.acquire()
    with pytest.raises(RateLimitExceeded):
        await limiter.acquire()


@pytest.mark.asyncio
async def test_circuit_opens_after_threshold(redis: fakeredis.FakeRedis) -> None:
    lim = RedisRateLimiter(
        redis, "cb-src", calls_per_minute=1000, failure_threshold=3, reset_seconds=60
    )
    for _ in range(3):
        await lim.record_failure()
    assert await lim.is_circuit_open()


@pytest.mark.asyncio
async def test_circuit_blocks_acquire(redis: fakeredis.FakeRedis) -> None:
    lim = RedisRateLimiter(
        redis, "open-src", calls_per_minute=1000, failure_threshold=2, reset_seconds=60
    )
    await lim.record_failure()
    await lim.record_failure()
    with pytest.raises(CircuitOpen):
        await lim.acquire()


@pytest.mark.asyncio
async def test_success_clears_failure_counter(redis: fakeredis.FakeRedis) -> None:
    lim = RedisRateLimiter(
        redis, "reset-src", calls_per_minute=1000, failure_threshold=3, reset_seconds=60
    )
    await lim.record_failure()
    await lim.record_failure()
    await lim.record_success()
    await lim.record_failure()
    assert not await lim.is_circuit_open()


@pytest.mark.asyncio
async def test_circuit_auto_resets_after_cooldown(redis: fakeredis.FakeRedis) -> None:
    lim = RedisRateLimiter(
        redis, "time-src", calls_per_minute=1000, failure_threshold=1, reset_seconds=0
    )
    await lim.record_failure()
    time.sleep(0.01)
    result = await lim.circuit_open_until()
    assert result is None
    await lim.acquire()
