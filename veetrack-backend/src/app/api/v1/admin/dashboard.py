"""Admin dashboard aggregate endpoint — Phase 26.

GET /api/v1/admin/dashboard
  Returns a single aggregate snapshot:
  - per-source quota usage + circuit-breaker state (Phase 07–10)
  - Celery queue depths for all four queues (Phase 05 Redis)
  - pending-review recommendation count (Phase 17)
  - recent error rate: count of ERROR-level log rows in last 1 h from
    the api_error_counts in-memory counter (no extra DB table needed;
    accurate for a single-process deployment; replace with Sentry summary
    if running multi-replica)

All data is read-only — no business logic is altered.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.container import get_cache_gateway, get_db_session
from app.core.security_deps import require_role
from app.domain.interfaces.services import CacheGateway
from app.domain.value_objects.role import Role

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/admin/dashboard", tags=["admin"])

# ---------------------------------------------------------------------------
# In-process error counter (incremented by the unhandled exception handler)
# ---------------------------------------------------------------------------

_error_window: list[float] = []  # timestamps of recent errors (monotonic)
_ERROR_WINDOW_SECONDS = 3600  # 1-hour sliding window


def record_api_error() -> None:
    """Increment the sliding-window error counter.  Called from error_handlers.py."""
    now = time.monotonic()
    _error_window.append(now)
    # Evict entries older than the window
    cutoff = now - _ERROR_WINDOW_SECONDS
    while _error_window and _error_window[0] < cutoff:
        _error_window.pop(0)


def get_recent_error_count() -> int:
    now = time.monotonic()
    cutoff = now - _ERROR_WINDOW_SECONDS
    return sum(1 for t in _error_window if t >= cutoff)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class SourceSnapshot(BaseModel):
    id: str
    type: str
    is_active: bool
    calls_made_this_window: int
    quota_limit: int
    circuit_open: bool
    usage_pct: float


class QueueDepths(BaseModel):
    ingestion: int
    nlp: int
    llm: int
    alerts: int


class DashboardResponse(BaseModel):
    generated_at: str
    sources: list[SourceSnapshot]
    queue_depths: QueueDepths
    pending_review_count: int
    errors_last_hour: int


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.get("", response_model=DashboardResponse)
async def get_dashboard(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    cache: Annotated[CacheGateway, Depends(get_cache_gateway)],
    _: Annotated[object, Depends(require_role(Role.admin))],
) -> DashboardResponse:
    """Return the admin dashboard aggregate snapshot."""
    from redis.asyncio import Redis

    from app.core.config import get_settings
    from app.infrastructure.connectors.base import _BUCKET_PREFIX, _OPEN_UNTIL_PREFIX
    from app.infrastructure.db.repositories.source import SqlAlchemySourceRepository

    settings = get_settings()

    # --- Sources -----------------------------------------------------------
    source_repo = SqlAlchemySourceRepository(session)
    sources = await source_repo.list_active()

    redis: Redis = Redis.from_url(settings.redis_url, decode_responses=False)
    source_snapshots: list[SourceSnapshot] = []
    try:
        minute = datetime.now(UTC).strftime("%Y%m%dT%H%M")
        for src in sources:
            calls_raw = await redis.get(f"{_BUCKET_PREFIX}{src.id}:{minute}")
            calls_made = int(calls_raw) if calls_raw else 0
            open_raw = await redis.get(f"{_OPEN_UNTIL_PREFIX}{src.id}")
            circuit_open = open_raw is not None and time.time() < float(open_raw)
            quota = max(1, int(src.rate_limit_budget * 60))
            source_snapshots.append(
                SourceSnapshot(
                    id=src.id,
                    type=src.type,
                    is_active=src.is_active,
                    calls_made_this_window=calls_made,
                    quota_limit=quota,
                    circuit_open=circuit_open,
                    usage_pct=min(100.0, round(calls_made / quota * 100, 1)),
                )
            )

        # --- Queue depths --------------------------------------------------
        depths: dict[str, int] = {}
        for q in ("ingestion", "nlp", "llm", "alerts"):
            raw = await redis.llen(q)
            depths[q] = int(raw) if raw else 0

    finally:
        await redis.aclose()

    # --- Pending review ----------------------------------------------------
    row = await session.execute(
        text("SELECT COUNT(*) FROM story_recommendations WHERE needs_human_review = true")
    )
    pending_count = int(row.scalar() or 0)

    return DashboardResponse(
        generated_at=datetime.now(UTC).isoformat(),
        sources=source_snapshots,
        queue_depths=QueueDepths(**depths),
        pending_review_count=pending_count,
        errors_last_hour=get_recent_error_count(),
    )
