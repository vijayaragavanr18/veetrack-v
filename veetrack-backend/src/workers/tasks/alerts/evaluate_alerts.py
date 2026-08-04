"""Celery task: evaluate_alerts — fires watchlist alerts for story updates.

Wires the two-tier EvaluateAlerts use case (fast-path + agentic) with:
  - The OllamaClient as the LLM gateway.
  - Four DB-backed read-only tools for the agentic path.
  - Pre-computed recent_alert_count so the use case stays injected/testable.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from celery import shared_task

logger = logging.getLogger(__name__)

# ── Configurable constants (mirror EvaluateAlerts defaults) ─────────────────
_RECENT_ALERT_WINDOW_HOURS = 24


# ── DB-backed tools (same pattern as generate_recommendation task) ───────────

def _make_alert_tools(session_factory: Any) -> dict[str, Any]:
    """Return the four alert-agent tools backed by the live DB session."""

    async def _q(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        from sqlalchemy import text
        async with session_factory() as session:
            result = await session.execute(text(sql), params)
            cols = result.keys()
            return [dict(zip(cols, row, strict=True)) for row in result]

    from app.infrastructure.llm.tools.get_alert_feedback_history import (
        get_alert_feedback_history as _feedback,
    )
    from app.infrastructure.llm.tools.get_entity_alert_history import (
        get_entity_alert_history as _entity_history,
    )
    from app.infrastructure.llm.tools.get_story_risk_context import (
        get_story_risk_context as _story_ctx,
    )
    from app.infrastructure.llm.tools.get_watchlist_preferences import (
        get_watchlist_preferences as _wl_prefs,
    )

    async def get_entity_alert_history(args: dict[str, Any]) -> str:
        return await _entity_history(args, _q)

    async def get_watchlist_preferences(args: dict[str, Any]) -> str:
        return await _wl_prefs(args, _q)

    async def get_story_risk_context(args: dict[str, Any]) -> str:
        return await _story_ctx(args, _q)

    async def get_alert_feedback_history(args: dict[str, Any]) -> str:
        return await _feedback(args, _q)

    return {
        "get_entity_alert_history": get_entity_alert_history,
        "get_watchlist_preferences": get_watchlist_preferences,
        "get_story_risk_context": get_story_risk_context,
        "get_alert_feedback_history": get_alert_feedback_history,
    }


# ── Main async runner ────────────────────────────────────────────────────────

async def _run(
    story_id: str,
    entity_id: str,
    workspace_id: str,
    risk_level: str,
) -> dict[str, Any]:
    import os

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.application.use_cases.watchlists.evaluate_alerts import (
        RECENT_ALERT_WINDOW_HOURS,
        EvaluateAlerts,
    )
    from app.infrastructure.db.repositories.watchlist import SqlAlchemyWatchlistRepository
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
        # Pre-compute recent alert count so the use case stays testable
        async with factory() as session:
            row = await session.execute(
                text(
                    "SELECT COUNT(*) FROM alerts a "
                    "JOIN watchlists w ON w.id = a.watchlist_id "
                    "WHERE w.entity_id = :eid "
                    "  AND a.sent_at >= NOW() - INTERVAL ':hours hours'"
                ),
                {"eid": entity_id, "hours": RECENT_ALERT_WINDOW_HOURS},
            )
            recent_alert_count = int(row.scalar() or 0)

            # Latest recommendation confidence for this story (may be None)
            conf_row = await session.execute(
                text(
                    "SELECT confidence_score FROM story_recommendations "
                    "WHERE story_id = :sid ORDER BY generated_at DESC LIMIT 1"
                ),
                {"sid": story_id},
            )
            conf_raw = conf_row.scalar()
            recommendation_confidence: float | None = (
                float(conf_raw) if conf_raw is not None else None
            )

        local_client = OllamaClient(model=llm_model, endpoint=llm_endpoint)
        gateway = RoutingLLMGateway(
            local_client=local_client,
            hosted_client=None,
            default_tier="local",
        )
        tools = _make_alert_tools(factory)

        async with factory() as session, session.begin():
            repo = SqlAlchemyWatchlistRepository(session)
            use_case = EvaluateAlerts(repo=repo, gateway=gateway, tools=tools)
            result = await use_case.execute(
                story_id=story_id,
                entity_id=entity_id,
                workspace_id=workspace_id,
                risk_level=risk_level,
                recent_alert_count=recent_alert_count,
                recommendation_confidence=recommendation_confidence,
            )

    finally:
        await engine.dispose()

    fired = len(result.fired)
    agentic = sum(1 for a in result.fired if a.agent_path == "agentic")
    logger.info(
        "evaluate_alerts.done",
        extra={
            "story_id": story_id,
            "fired": fired,
            "agentic": agentic,
            "skipped": result.skipped_count,
            "risk_level": risk_level,
        },
    )
    return {
        "fired": fired,
        "agentic": agentic,
        "skipped": result.skipped_count,
    }


@shared_task(
    name="alerts.evaluate_alerts",
    queue="alerts",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def evaluate_alerts(
    self: Any,
    story_id: str,
    entity_id: str,
    workspace_id: str,
    risk_level: str,
) -> dict[str, Any]:
    """Evaluate watchlists and fire alerts for a story update."""
    try:
        return asyncio.run(_run(story_id, entity_id, workspace_id, risk_level))
    except Exception as exc:
        logger.exception(
            "evaluate_alerts.failed",
            extra={"story_id": story_id, "entity_id": entity_id},
        )
        raise self.retry(exc=exc) from exc
