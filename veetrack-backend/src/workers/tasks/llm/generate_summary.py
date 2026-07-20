"""LLM task: generate an AI executive summary for a story cluster.

Triggered by the cluster_article task when an article joins a story that has
>= MIN_ARTICLES_FOR_SUMMARY members, OR on explicit request.

The task:
  1. Loads story title, member articles (headline, published_at, clean_content),
     and primary entity names from DB.
  2. Calls GenerateExecutiveSummary use case via RoutingLLMGateway.
  3. Upserts story_insights: keeps only the latest insight per story_id
     (deletes any prior row before inserting the new one).

No chain appended — this task is triggered selectively, not on every article.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from pydantic_settings import BaseSettings, SettingsConfigDict

from workers.celery_app import app

logger = structlog.get_logger(__name__)

MIN_ARTICLES_FOR_SUMMARY = 3


class SummarySettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = ""
    redis_url: str = "redis://localhost:6379/0"
    llm_local_endpoint: str = "http://localhost:8080/v1/chat/completions"
    llm_local_model: str = "Qwen/Qwen2.5-3B-Instruct"
    llm_min_articles: int = MIN_ARTICLES_FOR_SUMMARY


async def _run_generate(story_id: str, settings: SummarySettings) -> dict[str, Any]:
    from redis.asyncio import Redis
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    engine = create_async_engine(settings.database_url, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    redis: Redis = Redis.from_url(settings.redis_url, decode_responses=False)

    try:
        async with factory() as session:
            # 1. Count members
            count_row = await session.execute(
                text("SELECT COUNT(*) FROM story_articles WHERE story_id = :sid"),
                {"sid": story_id},
            )
            member_count = int(count_row.scalar() or 0)
            if member_count < settings.llm_min_articles:
                logger.info(
                    "generate_summary.too_few_articles",
                    story_id=story_id,
                    count=member_count,
                )
                return {"status": "skipped", "reason": "too_few_articles"}

            # 2. Load story title
            story_row = await session.execute(
                text("SELECT title FROM stories WHERE id = :id"),
                {"id": story_id},
            )
            story_result = story_row.first()
            if story_result is None:
                return {"status": "skipped", "reason": "story_not_found"}
            story_title = str(story_result[0] or "")

            # 3. Load articles (most recent first, cap at 10)
            art_rows = await session.execute(
                text(
                    "SELECT a.headline, a.published_at, a.clean_content "
                    "FROM articles a "
                    "JOIN story_articles sa ON sa.article_id = a.id "
                    "WHERE sa.story_id = :sid "
                    "ORDER BY a.published_at DESC "
                    "LIMIT 10"
                ),
                {"sid": story_id},
            )
            articles = [
                {
                    "headline": str(row.headline or ""),
                    "published_at": row.published_at.isoformat() if row.published_at else "",
                    "clean_content": str(row.clean_content or ""),
                }
                for row in art_rows
            ]

            # 4. Load entity names + primary_entity_id for cache invalidation
            entity_rows = await session.execute(
                text(
                    "SELECT e.canonical_name, s.primary_entity_id "
                    "FROM stories s "
                    "JOIN entities e ON e.id = s.primary_entity_id "
                    "WHERE s.id = :sid"
                ),
                {"sid": story_id},
            )
            entity_names = []
            primary_entity_id = ""
            for row in entity_rows:
                entity_names.append(str(row[0]))
                primary_entity_id = str(row[1])

        # 5. Build gateway
        from app.application.use_cases.insights.generate_executive_summary import (
            ArticleInput,
            GenerateExecutiveSummary,
        )
        from app.infrastructure.llm.llm_gateway import RoutingLLMGateway
        from app.infrastructure.llm.vllm_client import VllmClient

        local_client = VllmClient(
            model=settings.llm_local_model,
            endpoint=settings.llm_local_endpoint,
        )
        gateway = RoutingLLMGateway(
            local_client=local_client,
            hosted_client=None,
            redis=redis,
            default_tier="local",
        )
        use_case = GenerateExecutiveSummary(
            gateway=gateway,
            min_articles=settings.llm_min_articles,
        )

        article_inputs = [
            ArticleInput(
                headline=a["headline"],
                published_at=a["published_at"],
                clean_content=a["clean_content"],
            )
            for a in articles
        ]
        result = await use_case.run(
            story_id=story_id,
            story_title=story_title,
            articles=article_inputs,
            entity_names=entity_names,
        )

        if result.skipped:
            return {"status": "skipped", "reason": result.skip_reason}

        # 6. Upsert story_insights — delete existing, insert new
        async with factory() as session, session.begin():
            await session.execute(
                text("DELETE FROM story_insights WHERE story_id = :sid"),
                {"sid": story_id},
            )
            insight_id = str(uuid.uuid4())
            await session.execute(
                text(
                    "INSERT INTO story_insights "
                    "  (id, story_id, what_happened, why_happened, "
                    "   generated_at, model_used, token_cost) "
                    "VALUES (:id, :sid, :what, :why, :gen_at, :model, :cost)"
                ),
                {
                    "id": insight_id,
                    "sid": story_id,
                    "what": result.what_happened,
                    "why": result.why_happened,
                    "gen_at": datetime.now(UTC),
                    "model": result.model_used,
                    "cost": result.token_cost,
                },
            )

        logger.info(
            "generate_summary.saved",
            story_id=story_id,
            insight_id=insight_id,
            model=result.model_used,
        )

        # Invalidate feed cache so the new insight appears immediately
        if primary_entity_id:
            from workers.tasks.search.build_feed_cache import run as cache_run

            cache_run.apply_async(
                kwargs={"entity_id": primary_entity_id},
                queue="ingestion",
            )

        return {
            "status": "ok",
            "insight_id": insight_id,
            "model": result.model_used,
            "token_cost": result.token_cost,
        }

    finally:
        await redis.aclose()
        await engine.dispose()


@app.task(
    name="tasks.llm.generate_summary.run",
    queue="llm",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def run(self: object, *, story_id: str) -> dict[str, Any]:  # type: ignore[misc]
    """Generate (or regenerate) the executive summary for *story_id*."""
    settings = SummarySettings()
    if not settings.database_url:
        logger.warning("generate_summary.no_database_url", story_id=story_id)
        return {"status": "no_database_url"}
    try:
        return asyncio.run(_run_generate(story_id, settings))
    except Exception as exc:
        logger.error("generate_summary.failed", story_id=story_id, error=str(exc))
        raise
