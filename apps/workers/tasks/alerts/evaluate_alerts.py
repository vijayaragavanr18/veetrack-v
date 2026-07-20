"""Celery task: evaluate_alerts — fires watchlist alerts for high/critical stories."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from celery import shared_task

logger = logging.getLogger(__name__)


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
    """Evaluate watchlists and persist alert records for a story.

    Called by the NLP/LLM pipeline once a story risk level is determined.
    Returns {"fired": int, "skipped": int}.
    """
    try:
        return asyncio.run(_run(story_id, entity_id, workspace_id, risk_level))
    except Exception as exc:
        logger.exception(
            "evaluate_alerts.failed",
            extra={
                "story_id": story_id,
                "entity_id": entity_id,
                "workspace_id": workspace_id,
            },
        )
        raise self.retry(exc=exc) from exc


async def _run(
    story_id: str,
    entity_id: str,
    workspace_id: str,
    risk_level: str,
) -> dict[str, Any]:
    import os

    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

    from app.application.use_cases.watchlists.evaluate_alerts import EvaluateAlerts
    from app.infrastructure.db.repositories.watchlist import SqlAlchemyWatchlistRepository

    database_url = os.environ["DATABASE_URL"]
    engine = create_async_engine(database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session, session.begin():
        repo = SqlAlchemyWatchlistRepository(session)
        use_case = EvaluateAlerts(repo)
        result = await use_case.execute(story_id, entity_id, workspace_id, risk_level)

    await engine.dispose()

    fired_count = len(result.fired)
    logger.info(
        "evaluate_alerts.done",
        extra={
            "story_id": story_id,
            "fired": fired_count,
            "skipped": result.skipped_count,
        },
    )
    return {"fired": fired_count, "skipped": result.skipped_count}
