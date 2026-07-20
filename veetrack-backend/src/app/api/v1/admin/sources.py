"""Admin router: source management and quota usage dashboard.

GET  /api/v1/admin/sources         — list all sources with current quota usage
POST /api/v1/admin/sources         — create/seed a source row
GET  /api/v1/admin/sources/{id}    — single source + recent usage windows
"""

from __future__ import annotations

from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.container import get_db_session
from app.core.security_deps import require_role
from app.domain.entities import Source
from app.domain.value_objects.role import Role
from app.infrastructure.db.repositories.source import SqlAlchemySourceRepository

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/admin/sources", tags=["admin"])


class SourceUsageResponse(BaseModel):
    id: str
    type: str
    is_active: bool
    rate_limit_budget: float
    calls_made_this_window: int
    quota_limit: int
    circuit_open: bool


class CreateSourceRequest(BaseModel):
    type: str
    config_json: dict[str, Any] = {}
    is_active: bool = True
    rate_limit_budget: float = 1.0


class SourceResponse(BaseModel):
    id: str
    type: str
    is_active: bool
    rate_limit_budget: float


@router.get("", response_model=list[SourceUsageResponse])
async def list_sources(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    _: Annotated[object, Depends(require_role(Role.admin))],
) -> list[SourceUsageResponse]:
    """Return all sources with their current-window quota usage from Redis."""
    import time

    from redis.asyncio import Redis

    from app.core.config import get_settings
    from app.infrastructure.connectors.base import (
        _BUCKET_PREFIX,
        _OPEN_UNTIL_PREFIX,
    )

    settings = get_settings()
    source_repo = SqlAlchemySourceRepository(session)
    sources = await source_repo.list_active()

    redis: Redis = Redis.from_url(settings.redis_url, decode_responses=False)
    results: list[SourceUsageResponse] = []
    try:
        for src in sources:
            from datetime import UTC, datetime

            minute = datetime.now(UTC).strftime("%Y%m%dT%H%M")
            bucket_key = f"{_BUCKET_PREFIX}{src.id}:{minute}"
            open_until_key = f"{_OPEN_UNTIL_PREFIX}{src.id}"

            calls_raw = await redis.get(bucket_key)
            calls_made = int(calls_raw) if calls_raw else 0

            open_raw = await redis.get(open_until_key)
            circuit_open = False
            if open_raw is not None:
                circuit_open = time.time() < float(open_raw)

            calls_per_min = max(1, int(src.rate_limit_budget * 60))
            results.append(
                SourceUsageResponse(
                    id=src.id,
                    type=src.type,
                    is_active=src.is_active,
                    rate_limit_budget=src.rate_limit_budget,
                    calls_made_this_window=calls_made,
                    quota_limit=calls_per_min,
                    circuit_open=circuit_open,
                )
            )
    finally:
        await redis.aclose()

    return results


@router.post("", response_model=SourceResponse, status_code=201)
async def create_source(
    body: CreateSourceRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    _: Annotated[object, Depends(require_role(Role.admin))],
) -> SourceResponse:
    """Seed a new source row (used for initial setup and testing)."""
    source_repo = SqlAlchemySourceRepository(session)
    source = Source(
        type=body.type,  # type: ignore[arg-type]
        config_json=body.config_json,
        is_active=body.is_active,
        rate_limit_budget=body.rate_limit_budget,
    )
    saved = await source_repo.save(source)
    logger.info("admin.source_created", source_id=saved.id, type=saved.type)
    return SourceResponse(
        id=saved.id,
        type=saved.type,
        is_active=saved.is_active,
        rate_limit_budget=saved.rate_limit_budget,
    )


@router.get("/{source_id}", response_model=SourceUsageResponse)
async def get_source(
    source_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    _: Annotated[object, Depends(require_role(Role.admin))],
) -> SourceUsageResponse:
    import time
    from datetime import UTC, datetime

    from redis.asyncio import Redis

    from app.core.config import get_settings
    from app.infrastructure.connectors.base import _BUCKET_PREFIX, _OPEN_UNTIL_PREFIX

    settings = get_settings()
    source_repo = SqlAlchemySourceRepository(session)
    src = await source_repo.get_by_id(source_id)

    redis: Redis = Redis.from_url(settings.redis_url, decode_responses=False)
    try:
        minute = datetime.now(UTC).strftime("%Y%m%dT%H%M")
        calls_raw = await redis.get(f"{_BUCKET_PREFIX}{src.id}:{minute}")
        calls_made = int(calls_raw) if calls_raw else 0
        open_raw = await redis.get(f"{_OPEN_UNTIL_PREFIX}{src.id}")
        circuit_open = open_raw is not None and time.time() < float(open_raw)
    finally:
        await redis.aclose()

    calls_per_min = max(1, int(src.rate_limit_budget * 60))
    return SourceUsageResponse(
        id=src.id,
        type=src.type,
        is_active=src.is_active,
        rate_limit_budget=src.rate_limit_budget,
        calls_made_this_window=calls_made,
        quota_limit=calls_per_min,
        circuit_open=circuit_open,
    )
