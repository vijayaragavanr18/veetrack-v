"""LLM task: generate audience-specific recommendations for a story cluster.

Triggered from cluster_article._maybe_trigger_summary() alongside the summary task.
Runs on the llm queue.

Steps:
  1. Load story title, insight (what/why), article count + recent headlines, entity name.
  2. Call GenerateRecommendation use case via RoutingLLMGateway (hosted tier).
  3. Insert new recommendation rows (always new rows — recommendations accumulate over time).
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


class RecommendationSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = ""
    redis_url: str = "redis://localhost:6379/0"
    anthropic_api_key: str = ""
    llm_hosted_model: str = "claude-haiku-4-5-20251001"
    llm_local_endpoint: str = "http://localhost:8080/v1/chat/completions"
    llm_local_model: str = "Qwen/Qwen2.5-3B-Instruct-AWQ"
    llm_min_articles: int = 3
    recommendation_confidence_threshold: float = 0.65


async def _run_generate(story_id: str, settings: RecommendationSettings) -> dict[str, Any]:
    from redis.asyncio import Redis
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    engine = create_async_engine(settings.database_url, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    redis: Redis = Redis.from_url(settings.redis_url, decode_responses=False)

    try:
        async with factory() as session:
            # 1. Load story + insight
            story_row = await session.execute(
                text("SELECT title FROM stories WHERE id = :id"),
                {"id": story_id},
            )
            story_result = story_row.first()
            if story_result is None:
                return {"status": "skipped", "reason": "story_not_found"}
            story_title = str(story_result[0] or "")

            insight_row = await session.execute(
                text(
                    "SELECT what_happened, why_happened FROM story_insights "
                    "WHERE story_id = :sid ORDER BY generated_at DESC LIMIT 1"
                ),
                {"sid": story_id},
            )
            insight_result = insight_row.first()
            what_happened = str(insight_result[0]) if insight_result else ""
            why_happened = str(insight_result[1]) if insight_result else ""

            # 2. Count articles + recent headlines
            count_row = await session.execute(
                text("SELECT COUNT(*) FROM story_articles WHERE story_id = :sid"),
                {"sid": story_id},
            )
            article_count = int(count_row.scalar() or 0)

            headlines_rows = await session.execute(
                text(
                    "SELECT a.headline FROM articles a "
                    "JOIN story_articles sa ON sa.article_id = a.id "
                    "WHERE sa.story_id = :sid "
                    "ORDER BY a.published_at DESC LIMIT 8"
                ),
                {"sid": story_id},
            )
            recent_headlines = [str(row[0] or "") for row in headlines_rows if row[0]]

            # 3. Load entity name + primary_entity_id for cache invalidation
            entity_rows = await session.execute(
                text(
                    "SELECT e.canonical_name, s.primary_entity_id FROM stories s "
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

        # 4. Build gateway + run use case
        from app.application.use_cases.recommendations.generate_recommendation import (
            GenerateRecommendation,
        )
        from app.infrastructure.llm.hosted_client import HostedClient
        from app.infrastructure.llm.llm_gateway import RoutingLLMGateway
        from app.infrastructure.llm.vllm_client import VllmClient

        local_client = VllmClient(
            model=settings.llm_local_model,
            endpoint=settings.llm_local_endpoint,
        )
        hosted_client = HostedClient(
            model=settings.llm_hosted_model,
            api_key=settings.anthropic_api_key,
            db_url=settings.database_url,
            story_id=story_id,
        )
        gateway = RoutingLLMGateway(
            local_client=local_client,
            hosted_client=hosted_client,
            redis=redis,
            default_tier="local",
        )
        use_case = GenerateRecommendation(
            gateway=gateway,
            confidence_threshold=settings.recommendation_confidence_threshold,
            min_articles=settings.llm_min_articles,
        )

        output = await use_case.run(
            story_id=story_id,
            story_title=story_title,
            what_happened=what_happened,
            why_happened=why_happened,
            article_count=article_count,
            recent_headlines=recent_headlines,
            entity_names=entity_names,
        )

        if output.skipped:
            return {"status": "skipped", "reason": output.skip_reason}

        # 5. Persist recommendations
        async with factory() as session, session.begin():
            for rec in output.results:
                rec_id = str(uuid.uuid4())
                await session.execute(
                    text(
                        "INSERT INTO story_recommendations "
                        "  (id, story_id, recommendation_text, audience, "
                        "   risk_level, confidence_score, needs_human_review, generated_at) "
                        "VALUES (:id, :sid, :text, :audience, "
                        "        :risk, :conf, :review, :gen_at)"
                    ),
                    {
                        "id": rec_id,
                        "sid": story_id,
                        "text": rec.recommendation_text,
                        "audience": rec.audience,
                        "risk": rec.risk_level,
                        "conf": rec.confidence_score,
                        "review": rec.needs_human_review,
                        "gen_at": datetime.now(UTC),
                    },
                )

        pending = sum(1 for r in output.results if r.needs_human_review)
        logger.info(
            "generate_recommendation.saved",
            story_id=story_id,
            count=len(output.results),
            pending_review=pending,
        )

        # Invalidate feed cache so new recommendations appear immediately
        if primary_entity_id:
            from workers.tasks.search.build_feed_cache import run as cache_run

            cache_run.apply_async(
                kwargs={"entity_id": primary_entity_id},
                queue="ingestion",
            )

        return {
            "status": "ok",
            "story_id": story_id,
            "count": len(output.results),
            "pending_review": pending,
        }

    finally:
        await redis.aclose()
        await engine.dispose()


@app.task(
    name="tasks.llm.generate_recommendation.run",
    queue="llm",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def run(self: object, *, story_id: str) -> dict[str, Any]:  # type: ignore[misc]
    """Generate PR/exec/marketing recommendations for *story_id*."""
    settings = RecommendationSettings()
    if not settings.database_url:
        logger.warning("generate_recommendation.no_database_url", story_id=story_id)
        return {"status": "no_database_url"}
    try:
        return asyncio.run(_run_generate(story_id, settings))
    except Exception as exc:
        logger.error("generate_recommendation.failed", story_id=story_id, error=str(exc))
        raise
