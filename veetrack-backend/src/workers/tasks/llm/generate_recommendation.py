"""LLM task: generate audience-specific recommendations for a story cluster.

Triggered from cluster_article._maybe_trigger_summary() alongside the summary task.
Runs on the llm queue.

Steps:
  1. Load story metadata (title, risk_level, entity, insight, headlines).
  2. Optionally load days_since_last_event for hybrid trigger decision.
  3. Wire real DB-backed tools for the agentic path.
  4. Call GenerateRecommendation use case (agentic or single-shot depending on trigger).
  5. Insert recommendation rows including reasoning_trace + agent_mode.
"""

from __future__ import annotations

import asyncio
import json
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
    llm_local_endpoint: str = "http://localhost:11434/v1/chat/completions"
    llm_local_model: str = "qwen2.5:7b"
    llm_min_articles: int = 3
    recommendation_confidence_threshold: float = 0.65


# ── DB-backed tools ───────────────────────────────────────────────────────────

def _make_tools(session_factory: Any) -> dict[str, Any]:
    """Return the four ReAct tools backed by the live DB session factory."""

    async def get_story_cluster_context(args: dict[str, Any]) -> str:
        story_id = str(args.get("story_id", ""))
        from sqlalchemy import text
        async with session_factory() as session:
            rows = await session.execute(
                text(
                    "SELECT a.headline, a.published_at, a.clean_content "
                    "FROM articles a "
                    "JOIN story_articles sa ON sa.article_id = a.id "
                    "WHERE sa.story_id = :sid "
                    "ORDER BY a.published_at DESC LIMIT 15"
                ),
                {"sid": story_id},
            )
            items = [
                f"{row.headline} ({row.published_at}): {str(row.clean_content or '')[:100]}"
                for row in rows
            ]
        return "\n".join(items) if items else "No articles found for this story."

    async def get_entity_history(args: dict[str, Any]) -> str:
        entity_id = str(args.get("entity_id", ""))
        days = int(args.get("days", 30))
        from sqlalchemy import text
        async with session_factory() as session:
            rows = await session.execute(
                text(
                    "SELECT s.title, s.risk_level, s.updated_at "
                    "FROM stories s "
                    "WHERE s.primary_entity_id = :eid "
                    "  AND s.updated_at >= NOW() - INTERVAL ':days days' "
                    "ORDER BY s.updated_at DESC LIMIT 10"
                ),
                {"eid": entity_id, "days": days},
            )
            items = [
                f"{row.title} [risk={row.risk_level}] at {row.updated_at}"
                for row in rows
            ]
        return "\n".join(items) if items else f"No story activity in the past {days} days."

    async def get_similar_past_incidents(args: dict[str, Any]) -> str:
        entity_id = str(args.get("entity_id", ""))
        risk_level = str(args.get("risk_level", "medium"))
        from sqlalchemy import text
        async with session_factory() as session:
            rows = await session.execute(
                text(
                    "SELECT sr.recommendation_text, sr.audience, sr.needs_human_review, "
                    "       sr.agent_mode, sr.generated_at "
                    "FROM story_recommendations sr "
                    "JOIN stories s ON s.id = sr.story_id "
                    "WHERE s.primary_entity_id = :eid "
                    "  AND sr.risk_level = :risk "
                    "ORDER BY sr.generated_at DESC LIMIT 5"
                ),
                {"eid": entity_id, "risk": risk_level},
            )
            items = [
                f"[{row.audience}] {row.recommendation_text[:120]} "
                f"(review_needed={row.needs_human_review}, mode={row.agent_mode})"
                for row in rows
            ]
        return "\n".join(items) if items else "No similar past incidents found."

    async def get_watchlist_status(args: dict[str, Any]) -> str:
        entity_id = str(args.get("entity_id", ""))
        from sqlalchemy import text
        async with session_factory() as session:
            row = await session.execute(
                text(
                    "SELECT COUNT(*) FROM watchlist_items wi "
                    "JOIN watchlists w ON w.id = wi.watchlist_id "
                    "WHERE wi.entity_id = :eid AND w.is_active = true"
                ),
                {"eid": entity_id},
            )
            count = int(row.scalar() or 0)
        if count == 0:
            return "No active users are watching this entity."
        return f"{count} active watchlist(s) include this entity — alerts will reach real users."

    return {
        "get_story_cluster_context": get_story_cluster_context,
        "get_entity_history": get_entity_history,
        "get_similar_past_incidents": get_similar_past_incidents,
        "get_watchlist_status": get_watchlist_status,
    }


# ── Main async runner ─────────────────────────────────────────────────────────

async def _run_generate(story_id: str, settings: RecommendationSettings) -> dict[str, Any]:
    from redis.asyncio import Redis
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    engine = create_async_engine(settings.database_url, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    redis: Redis = Redis.from_url(settings.redis_url, decode_responses=False)

    try:
        async with factory() as session:
            # 1. Load story + risk_level
            story_row = await session.execute(
                text("SELECT title, risk_level, primary_entity_id FROM stories WHERE id = :id"),
                {"id": story_id},
            )
            story_result = story_row.first()
            if story_result is None:
                return {"status": "skipped", "reason": "story_not_found"}
            story_title = str(story_result[0] or "")
            risk_level = str(story_result[1] or "low")
            primary_entity_id = str(story_result[2] or "")

            # 2. Load insight
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

            # 3. Article count + headlines
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

            # 4. Entity names
            entity_rows = await session.execute(
                text(
                    "SELECT e.canonical_name FROM stories s "
                    "JOIN entities e ON e.id = s.primary_entity_id "
                    "WHERE s.id = :sid"
                ),
                {"sid": story_id},
            )
            entity_names = [str(row[0]) for row in entity_rows]

            # 5. Days since last event (for hybrid trigger)
            last_event_row = await session.execute(
                text(
                    "SELECT EXTRACT(DAY FROM NOW() - MAX(s.updated_at))::int "
                    "FROM stories s "
                    "WHERE s.primary_entity_id = :eid AND s.id != :sid"
                ),
                {"eid": primary_entity_id, "sid": story_id},
            )
            days_since_raw = last_event_row.scalar()
            days_since_last_event: int | None = int(days_since_raw) if days_since_raw is not None else None

        # 6. Build gateway + tools
        from app.application.use_cases.recommendations.generate_recommendation import (
            GenerateRecommendation,
        )
        from app.infrastructure.llm.llm_gateway import RoutingLLMGateway
        from app.infrastructure.llm.ollama_client import OllamaClient

        local_client = OllamaClient(
            model=settings.llm_local_model,
            endpoint=settings.llm_local_endpoint,
        )
        gateway = RoutingLLMGateway(
            local_client=local_client,
            hosted_client=None,
            redis=redis,
            default_tier="local",
        )
        tools = _make_tools(factory)
        use_case = GenerateRecommendation(
            gateway=gateway,
            confidence_threshold=settings.recommendation_confidence_threshold,
            min_articles=settings.llm_min_articles,
            tools=tools,
        )

        output = await use_case.run(
            story_id=story_id,
            story_title=story_title,
            what_happened=what_happened,
            why_happened=why_happened,
            article_count=article_count,
            recent_headlines=recent_headlines,
            entity_names=entity_names,
            entity_id=primary_entity_id,
            risk_level=risk_level,
            days_since_last_event=days_since_last_event,
        )

        if output.skipped:
            return {"status": "skipped", "reason": output.skip_reason}

        # 7. Persist — now includes agent_mode + reasoning_trace
        async with factory() as session, session.begin():
            for rec in output.results:
                rec_id = str(uuid.uuid4())
                await session.execute(
                    text(
                        "INSERT INTO story_recommendations "
                        "  (id, story_id, recommendation_text, audience, "
                        "   risk_level, confidence_score, needs_human_review, "
                        "   generated_at, agent_mode, reasoning_trace) "
                        "VALUES (:id, :sid, :text, :audience, "
                        "        :risk, :conf, :review, :gen_at, :mode, :trace)"
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
                        "mode": rec.agent_mode,
                        "trace": json.dumps(rec.reasoning_trace) if rec.reasoning_trace else "[]",
                    },
                )

        agentic_count = sum(1 for r in output.results if r.agent_mode == "agentic")
        pending = sum(1 for r in output.results if r.needs_human_review)
        logger.info(
            "generate_recommendation.saved",
            story_id=story_id,
            count=len(output.results),
            agentic=agentic_count,
            pending_review=pending,
            risk_level=risk_level,
        )

        # Invalidate feed cache
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
            "agentic": agentic_count,
            "pending_review": pending,
            "risk_level": risk_level,
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
