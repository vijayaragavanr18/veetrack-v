"""Unit tests: RedisRateLimiter — token bucket and circuit breaker."""

from __future__ import annotations

import time

import fakeredis.aioredis as fakeredis
import pytest

from app.domain.exceptions import ServiceUnavailableError
from app.infrastructure.connectors.base import RedisRateLimiter


@pytest.fixture()
async def redis() -> fakeredis.FakeRedis:
    return fakeredis.FakeRedis(decode_responses=False)


@pytest.fixture()
def limiter(redis: fakeredis.FakeRedis) -> RedisRateLimiter:
    return RedisRateLimiter(redis, source_id="test-src", calls_per_minute=3)


@pytest.mark.asyncio
async def test_allows_calls_within_quota(limiter: RedisRateLimiter) -> None:
    """Three calls within one minute window should all succeed."""
    await limiter.acquire()
    await limiter.acquire()
    await limiter.acquire()


@pytest.mark.asyncio
async def test_blocks_call_exceeding_quota(limiter: RedisRateLimiter) -> None:
    """The 4th call in the same window should raise ServiceUnavailableError."""
    await limiter.acquire()
    await limiter.acquire()
    await limiter.acquire()
    with pytest.raises(ServiceUnavailableError, match="rate limit"):
        await limiter.acquire()


@pytest.mark.asyncio
async def test_circuit_opens_after_failures(
    redis: fakeredis.FakeRedis,
) -> None:
    """After CIRCUIT_FAILURE_THRESHOLD failures the circuit opens."""

    lim = RedisRateLimiter(
        redis,
        source_id="cb-src",
        calls_per_minute=1000,
        failure_threshold=3,
        reset_seconds=60,
    )
    for _ in range(3):
        await lim.record_failure()

    assert await lim.is_circuit_open()


@pytest.mark.asyncio
async def test_circuit_open_blocks_acquire(redis: fakeredis.FakeRedis) -> None:
    """An open circuit raises ServiceUnavailableError immediately."""
    lim = RedisRateLimiter(
        redis,
        source_id="open-src",
        calls_per_minute=1000,
        failure_threshold=2,
        reset_seconds=60,
    )
    await lim.record_failure()
    await lim.record_failure()

    with pytest.raises(ServiceUnavailableError, match="circuit open"):
        await lim.acquire()


@pytest.mark.asyncio
async def test_success_resets_failure_counter(redis: fakeredis.FakeRedis) -> None:
    """recording success clears the failure counter so circuit won't open."""
    lim = RedisRateLimiter(
        redis,
        source_id="reset-src",
        calls_per_minute=1000,
        failure_threshold=3,
        reset_seconds=60,
    )
    await lim.record_failure()
    await lim.record_failure()
    await lim.record_success()
    # One more failure after reset — should not open the circuit
    await lim.record_failure()
    assert not await lim.is_circuit_open()


@pytest.mark.asyncio
async def test_circuit_auto_resets_after_cooldown(redis: fakeredis.FakeRedis) -> None:
    """Circuit auto-resets after cooldown elapses (tested with 0-second reset)."""
    lim = RedisRateLimiter(
        redis,
        source_id="reset-time-src",
        calls_per_minute=1000,
        failure_threshold=1,
        reset_seconds=0,  # immediate reset
    )
    await lim.record_failure()
    # Tiny sleep to let reset_seconds=0 expire
    time.sleep(0.01)
    # circuit_open_until should clear the key when it checks
    result = await lim.circuit_open_until()
    assert result is None
    # acquire should succeed
    await lim.acquire()
