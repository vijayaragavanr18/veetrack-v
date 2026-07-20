"""Use case: retrieve liveness / readiness status."""

from __future__ import annotations

from app.application.dto.health import HealthResponse, ReadinessResponse, VersionResponse
from app.core.config import Settings
from app.domain.interfaces.services import CacheGateway


class GetHealthStatus:
    """Returns liveness and readiness information for the API."""

    def __init__(self, cache: CacheGateway, settings: Settings) -> None:
        self._cache = cache
        self._settings = settings

    async def liveness(self) -> HealthResponse:
        """Return OK if the process is running."""
        return HealthResponse(status="ok")

    async def readiness(self) -> ReadinessResponse:
        """Check each dependency and return an aggregate status.

        Currently checks: Redis.
        TODO Phase 04: add database connection check.
        """
        checks: dict[str, str] = {}

        cache_ok = await self._cache.ping()
        checks["redis"] = "ok" if cache_ok else "unavailable"

        overall = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
        return ReadinessResponse(status=overall, checks=checks)

    async def version(self) -> VersionResponse:
        """Return the running API version and environment."""
        return VersionResponse(
            version=self._settings.api_version,
            environment=self._settings.environment,
        )
