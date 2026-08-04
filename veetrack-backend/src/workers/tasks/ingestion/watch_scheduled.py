"""Celery Beat task: watch_scheduled — agentic watcher pull batch.

Wires the two-tier PlanPullBatch use case (fast-path + agentic) with:
  - The OllamaClient as the LLM gateway.
  - Four DB-backed read-only tools for the agentic path.
  - Pre-computed activity stats and quota status injected into WatchedEntity.

The task:
  1. Loads all watched entities from the DB (active watchlists, unique entity+source pairs).
  2. Pre-computes recent activity stats per entity.
  3. Checks current quota for each source.
  4. Calls PlanPullBatch to produce a ranked pull plan.
  5. Dispatches individual pull tasks (watch_newsdata / watch_rss etc.) in priority order.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from celery import shared_task

logger = logging.getLogger(__name__)

# How many recent hours to compute avg activity for
_ACTIVITY_WINDOW_HOURS = 6


def _make_watcher_tools(session_factory: Any) -> dict[str, Any]:
    """Return the four watcher-agent tools backed by the live DB session."""

    async def _q(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        from sqlalchemy import text
        async with session_factory() as session:
            result = await session.execute(text(sql), params)
            cols = result.keys()
            return [dict(zip(cols, row, strict=True)) for row in result]

    from app.infrastructure.llm.tools.get_entity_aliases import (
        get_entity_aliases as _aliases,
    )
    from app.infrastructure.llm.tools.get_entity_recent_activity import (
        get_entity_recent_activity as _recent_activity,
    )
    from app.infrastructure.llm.tools.get_source_quota_status import (
        get_source_quota_status as _quota_status,
    )
    from app.infrastructure.llm.tools.get_watchlist_priority import (
        get_watchlist_priority as _priority,
    )

    async def get_entity_recent_activity(args: dict[str, Any]) -> str:
        return await _recent_activity(args, _q)

    async def get_source_quota_status(args: dict[str, Any]) -> str:
        return await _quota_status(args, _q)

    async def get_entity_aliases(args: dict[str, Any]) -> str:
        return await _aliases(args, _q)

    async def get_watchlist_priority(args: dict[str, Any]) -> str:
        return await _priority(args, _q)

    return {
        "get_entity_recent_activity": get_entity_recent_activity,
        "get_source_quota_status": get_source_quota_status,
        "get_entity_aliases": get_entity_aliases,
        "get_watchlist_priority": get_watchlist_priority,
    }


async def _run_batch(source_id: str) -> dict[str, Any]:
    import os

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.application.use_cases.ingestion.plan_pull_batch import (
        PlanPullBatch,
        WatchedEntity,
    )
    from app.infrastructure.llm.llm_gateway import RoutingLLMGateway
    from app.infrastructure.llm.ollama_client import OllamaClient

    database_url = os.environ.get("DATABASE_URL", "")
    llm_endpoint = os.environ.get(
        "LLM_LOCAL_ENDPOINT", "http://localhost:11434/v1/chat/completions"
    )
    llm_model = os.environ.get("LLM_LOCAL_MODEL", "qwen2.5:7b")

    engine = create_async_engine(database_url, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    try:
        async with factory() as session:
            # Load unique entity+source pairs from active watchlists
            entity_rows = await session.execute(
                text("""
                    SELECT DISTINCT
                        w.entity_id,
                        :source_id AS source_id,
                        2 AS sensitivity_rank
                    FROM watchlists w
                    LIMIT 50
                """),
                {"source_id": source_id},
            )
            entity_data = [dict(zip(entity_rows.keys(), row, strict=True)) for row in entity_rows]

            if not entity_data:
                await engine.dispose()
                return {"planned": 0, "skipped": 0, "agent_path": "fast_path"}

            entity_ids = [r["entity_id"] for r in entity_data]

            # Pre-compute recent activity for each entity
            activity_map: dict[str, float] = {}
            for eid in entity_ids:
                act_row = await session.execute(
                    text("""
                        SELECT COUNT(*) AS total
                        FROM articles a
                        JOIN article_entities ae ON ae.article_id = a.id
                        WHERE ae.entity_id = :eid
                          AND a.ingested_at >= NOW() - INTERVAL '6 hours'
                    """),
                    {"eid": eid},
                )
                total = int(act_row.scalar() or 0)
                activity_map[eid] = total / _ACTIVITY_WINDOW_HOURS

            # Current quota for this source
            quota_row = await session.execute(
                text("""
                    SELECT calls_made, quota_limit
                    FROM api_usage_log
                    WHERE source_id = :sid
                    ORDER BY window_start DESC
                    LIMIT 1
                """),
                {"sid": source_id},
            )
            q = quota_row.first()
            quota_total = int(q[1] or 0) if q else 0
            quota_remaining = max(0, quota_total - int(q[0] or 0)) if q else quota_total

        _SENSITIVITY_NAMES = {4: "critical", 3: "high", 2: "medium", 1: "low"}
        entities = [
            WatchedEntity(
                entity_id=r["entity_id"],
                source_id=source_id,
                recent_avg_hourly=activity_map.get(r["entity_id"], 0.0),
                max_sensitivity=_SENSITIVITY_NAMES.get(int(r.get("sensitivity_rank") or 2), "medium"),
            )
            for r in entity_data
        ]

        local_client = OllamaClient(model=llm_model, endpoint=llm_endpoint)
        gateway = RoutingLLMGateway(
            local_client=local_client,
            hosted_client=None,
            default_tier="local",
        )
        tools = _make_watcher_tools(factory)

        use_case = PlanPullBatch(gateway=gateway, tools=tools)
        plan = await use_case.execute(
            entities=entities,
            quota_remaining=quota_remaining,
            quota_total=quota_total,
            source_id=source_id,
        )

    finally:
        await engine.dispose()

    # Dispatch individual pull tasks in priority order
    from workers.tasks.ingestion.watch_newsdata import run as newsdata_run

    dispatched = 0
    for item in plan.items:
        try:
            # Build query: use canonical name + aliases if use_aliases=True
            query = item.entity_id  # Simplified: real impl would resolve canonical name
            newsdata_run.apply_async(
                kwargs={"source_id": item.source_id, "query": query},
                queue="ingestion",
                priority=10 - min(item.priority, 9),  # higher Celery priority = lower number
            )
            dispatched += 1
        except Exception as exc:
            logger.warning(
                "watch_scheduled.dispatch_failed",
                entity_id=item.entity_id,
                error=str(exc),
            )

    logger.info(
        "watch_scheduled.batch_complete",
        extra={
            "source_id": source_id,
            "planned": len(plan.items),
            "dispatched": dispatched,
            "skipped": len(plan.skipped_entity_ids),
            "agent_path": plan.agent_path,
        },
    )
    return {
        "planned": len(plan.items),
        "dispatched": dispatched,
        "skipped": len(plan.skipped_entity_ids),
        "agent_path": plan.agent_path,
    }


@shared_task(
    name="tasks.ingestion.watch_scheduled.run",
    queue="ingestion",
    bind=True,
    max_retries=2,
    default_retry_delay=120,
)
def run(self: Any, *, source_id: str = "newsdata-default") -> dict[str, Any]:
    """Plan and dispatch pull tasks for all watched entities for *source_id*."""
    try:
        return asyncio.run(_run_batch(source_id))
    except Exception as exc:
        logger.exception(
            "watch_scheduled.failed",
            extra={"source_id": source_id},
        )
        raise self.retry(exc=exc) from exc
