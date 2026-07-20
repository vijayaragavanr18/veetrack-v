"""Health and version DTOs."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Liveness probe response."""

    status: str


class ReadinessResponse(BaseModel):
    """Readiness probe response — reports per-dependency health."""

    status: str
    checks: dict[str, str]


class VersionResponse(BaseModel):
    """Version response returned by GET /version."""

    version: str
    environment: str
