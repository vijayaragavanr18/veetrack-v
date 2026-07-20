"""Unit tests for the DI container — resolves providers without real infrastructure."""

from __future__ import annotations

import pytest

from app.application.use_cases.get_health_status import GetHealthStatus
from app.core.config import get_settings
from tests.conftest import FakeCacheGateway


def test_fake_cache_satisfies_protocol() -> None:
    """FakeCacheGateway is a valid CacheGateway (structural subtype check)."""
    from app.domain.interfaces.services import CacheGateway

    fake = FakeCacheGateway()
    assert isinstance(fake, CacheGateway)


@pytest.mark.asyncio
async def test_health_use_case_with_fake_cache() -> None:
    """GetHealthStatus resolves and returns liveness OK with a fake cache."""
    settings = get_settings()
    fake = FakeCacheGateway()
    use_case = GetHealthStatus(cache=fake, settings=settings)

    result = await use_case.liveness()
    assert result.status == "ok"


@pytest.mark.asyncio
async def test_readiness_ok_when_cache_available() -> None:
    """Readiness returns ok when all dependencies are up."""
    settings = get_settings()
    fake = FakeCacheGateway(available=True)
    use_case = GetHealthStatus(cache=fake, settings=settings)

    result = await use_case.readiness()
    assert result.status == "ok"
    assert result.checks["redis"] == "ok"


@pytest.mark.asyncio
async def test_readiness_degraded_when_cache_down() -> None:
    """Readiness returns degraded when cache is unavailable."""
    settings = get_settings()
    fake = FakeCacheGateway(available=False)
    use_case = GetHealthStatus(cache=fake, settings=settings)

    result = await use_case.readiness()
    assert result.status == "degraded"
    assert result.checks["redis"] == "unavailable"
