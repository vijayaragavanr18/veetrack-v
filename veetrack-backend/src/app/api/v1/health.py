"""Health and version endpoints.

Routes:
  GET /api/v1/health        — liveness probe (process up)
  GET /api/v1/health/ready  — readiness probe (dependencies reachable)
  GET /api/v1/version       — running version and environment
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException

from app.application.dto.health import HealthResponse, ReadinessResponse, VersionResponse
from app.application.use_cases.get_health_status import GetHealthStatus
from app.core.container import get_health_use_case

router = APIRouter(tags=["health"])
logger = structlog.get_logger(__name__)


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
async def health(
    use_case: Annotated[GetHealthStatus, Depends(get_health_use_case)],
) -> HealthResponse:
    """Return 200 as long as the process is running.

    Suitable for use as a Kubernetes liveness probe — no dependency checks.
    """
    return await use_case.liveness()


@router.get("/health/ready", response_model=ReadinessResponse, summary="Readiness probe")
async def health_ready(
    use_case: Annotated[GetHealthStatus, Depends(get_health_use_case)],
) -> ReadinessResponse:
    """Return 200 when all critical dependencies are reachable.

    Returns 503 with a per-check breakdown if any dependency is unavailable.
    Suitable for use as a Kubernetes readiness probe.
    """
    result = await use_case.readiness()
    if result.status != "ok":
        logger.warning("health.readiness.degraded", checks=result.checks)
        raise HTTPException(
            status_code=503,
            detail=result.model_dump(),
        )
    return result


@router.get("/version", response_model=VersionResponse, summary="Running version")
async def version(
    use_case: Annotated[GetHealthStatus, Depends(get_health_use_case)],
) -> VersionResponse:
    """Return the current API version string and runtime environment."""
    return await use_case.version()
