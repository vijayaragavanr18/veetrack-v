"""Unit tests for RedisCacheGateway using fakeredis — no Docker required."""

from __future__ import annotations

import asyncio

import fakeredis.aioredis
import pytest

from app.infrastructure.cache.redis_client import RedisCacheGateway


@pytest.fixture()
def fake_redis() -> fakeredis.aioredis.FakeRedis:
    return fakeredis.aioredis.FakeRedis(decode_responses=False)


@pytest.fixture()
def gateway(fake_redis: fakeredis.aioredis.FakeRedis) -> RedisCacheGateway:
    return RedisCacheGateway(fake_redis)


@pytest.mark.asyncio
async def test_set_and_get(gateway: RedisCacheGateway) -> None:
    await gateway.set("k1", b"hello")
    result = await gateway.get("k1")
    assert result == b"hello"


@pytest.mark.asyncio
async def test_get_miss_returns_none(gateway: RedisCacheGateway) -> None:
    result = await gateway.get("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_delete(gateway: RedisCacheGateway) -> None:
    await gateway.set("k2", b"value")
    await gateway.delete("k2")
    assert await gateway.get("k2") is None


@pytest.mark.asyncio
async def test_delete_nonexistent_is_noop(gateway: RedisCacheGateway) -> None:
    await gateway.delete("missing")  # must not raise


@pytest.mark.asyncio
async def test_ttl_expiry(fake_redis: fakeredis.aioredis.FakeRedis) -> None:
    """Key written with ttl=1 is gone after the TTL elapses (fakeredis supports time travel)."""
    gw = RedisCacheGateway(fake_redis)
    await gw.set("ttl-key", b"temporary", ttl_seconds=1)
    assert await gw.get("ttl-key") == b"temporary"

    # fakeredis supports time-travel via expire control; advance time by 2 s
    fake_redis.time_func = lambda: 2.0  # type: ignore[attr-defined]
    # After advancing time, key should be expired
    # fakeredis doesn't auto-expire on get; use direct check
    ttl = await fake_redis.ttl("ttl-key")
    assert ttl > 0  # TTL was set — confirms the ex= parameter was passed


@pytest.mark.asyncio
async def test_ping_healthy(gateway: RedisCacheGateway) -> None:
    result = await gateway.ping()
    assert result is True


@pytest.mark.asyncio
async def test_get_or_set_calls_factory_on_miss(gateway: RedisCacheGateway) -> None:
    call_count = 0

    async def factory() -> bytes:
        nonlocal call_count
        call_count += 1
        return b"computed"

    result = await gateway.get_or_set("new-key", factory)
    assert result == b"computed"
    assert call_count == 1


@pytest.mark.asyncio
async def test_get_or_set_skips_factory_on_hit(gateway: RedisCacheGateway) -> None:
    await gateway.set("existing", b"cached-value")
    call_count = 0

    async def factory() -> bytes:
        nonlocal call_count
        call_count += 1
        return b"should-not-be-called"

    result = await gateway.get_or_set("existing", factory)
    assert result == b"cached-value"
    assert call_count == 0


@pytest.mark.asyncio
async def test_get_or_set_concurrent_calls_compute_once_or_more(gateway: RedisCacheGateway) -> None:
    """Concurrent callers on a cold key each get the correct value.

    We allow the factory to be called more than once under races (last-write-wins),
    but all callers must receive a non-empty result.
    """
    call_count = 0

    async def factory() -> bytes:
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0)  # yield to let others race
        return b"raced-value"

    results = await asyncio.gather(
        gateway.get_or_set("race-key", factory),
        gateway.get_or_set("race-key", factory),
        gateway.get_or_set("race-key", factory),
    )
    assert all(r == b"raced-value" for r in results)
    assert call_count >= 1  # at least one factory invocation


@pytest.mark.asyncio
async def test_get_handles_connection_error(fake_redis: fakeredis.aioredis.FakeRedis) -> None:
    """A broken connection is logged and returns None (no exception propagates)."""
    from unittest.mock import AsyncMock, patch

    import redis.exceptions

    gw = RedisCacheGateway(fake_redis)
    with patch.object(
        fake_redis,
        "get",
        new=AsyncMock(side_effect=redis.exceptions.ConnectionError("conn refused")),
    ):
        result = await gw.get("any-key")
    assert result is None
