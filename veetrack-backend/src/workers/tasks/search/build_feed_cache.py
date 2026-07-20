"""Search task: build (or rebuild) the full 4-page feed cache for an entity.

Triggered by:
  - Cluster update (cluster_article joins/creates a story)
  - LLM tasks completing (summary / recommendation)
  - Cold Path cache miss for a known entity

Writes a JSON payload to Redis keyed by entity_id:
  vt:feed:{entity_id}  → serialised list[StoryPayload]  TTL=300s

Explicit invalidation: callers must call this task rather than relying only
on TTL expiry — stale data is never served past an update.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog
from pydantic_settings import BaseSettings, SettingsConfigDict

from workers.celery_app import app

logger = structlog.get_logger(__name__)

_FEED_KEY_PREFIX = "vt:feed:"
_TRACKED_KEY_PREFIX = "vt:tracked:"
_CACHE_TTL = 300  # 5 minutes — always explicitly refreshed on story update
_STORY_LIMIT = 50  # max stories per entity in cached payload
_ARTICLE_PREVIEW = 5  # articles per story for Page-1


class CacheSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = ""
    redis_url: str = "redis://localhost:6379/0"
    feed_cache_ttl: int = _CACHE_TTL
    feed_story_limit: int = _STORY_LIMIT


async def _build_payload(entity_id: str, settings: CacheSettings) -> int:
    """Build + write the payload; return the number of stories written."""
    from redis.asyncio import Redis
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    engine = create_async_engine(settings.database_url, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    redis: Redis = Redis.from_url(settings.redis_url, decode_responses=False)

    try:
        async with factory() as session:
            # 1. Entity name
            ent_row = await session.execute(
                text("SELECT canonical_name FROM entities WHERE id = :id"),
                {"id": entity_id},
            )
            ent_result = ent_row.first()
            if ent_result is None:
                logger.warning("build_feed_cache.entity_not_found", entity_id=entity_id)
                return 0
            entity_name = str(ent_result[0])

            # 2. Active stories for this entity, newest first
            story_rows = await session.execute(
                text(
                    "SELECT s.id, s.title, s.status, s.risk_level, s.updated_at, "
                    "       COUNT(sa.article_id) AS article_count "
                    "FROM stories s "
                    "LEFT JOIN story_articles sa ON sa.story_id = s.id "
                    "WHERE s.primary_entity_id = :eid AND s.status = 'active' "
                    "GROUP BY s.id "
                    "ORDER BY s.updated_at DESC "
                    "LIMIT :lim"
                ),
                {"eid": entity_id, "lim": settings.feed_story_limit},
            )
            stories = list(story_rows)
            if not stories:
                return 0

            story_ids = [str(s.id) for s in stories]

            # 3. Articles (Page 1 preview)
            art_rows = await session.execute(
                text(
                    "SELECT a.id, a.headline, a.publisher, a.published_at, "
                    "       a.sentiment_label, sa.story_id "
                    "FROM articles a "
                    "JOIN story_articles sa ON sa.article_id = a.id "
                    "WHERE sa.story_id = ANY(:sids) "
                    "ORDER BY a.published_at DESC"
                ),
                {"sids": story_ids},
            )
            articles_by_story: dict[str, list[dict[str, Any]]] = {}
            for ar in art_rows:
                sid = str(ar.story_id)
                if len(articles_by_story.get(sid, [])) < _ARTICLE_PREVIEW:
                    articles_by_story.setdefault(sid, []).append(
                        {
                            "id": str(ar.id),
                            "headline": ar.headline or "",
                            "publisher": ar.publisher or "",
                            "published_at": ar.published_at.isoformat() if ar.published_at else "",
                            "sentiment_label": ar.sentiment_label or "neutral",
                        }
                    )

            # 4. Insights (Page 2)
            if story_ids:
                insight_rows = await session.execute(
                    text(
                        "SELECT story_id, what_happened, why_happened, model_used "
                        "FROM story_insights "
                        "WHERE story_id = ANY(:sids) "
                        "ORDER BY generated_at DESC"
                    ),
                    {"sids": story_ids},
                )
                insights: dict[str, dict[str, Any]] = {}
                for ir in insight_rows:
                    sid = str(ir.story_id)
                    if sid not in insights:
                        insights[sid] = {
                            "what_happened": ir.what_happened or "",
                            "why_happened": ir.why_happened or "",
                            "model_used": ir.model_used or "",
                        }
            else:
                insights = {}

            # 5. Cluster member IDs (Page 3)
            cluster_rows = await session.execute(
                text("SELECT story_id, article_id FROM story_articles WHERE story_id = ANY(:sids)"),
                {"sids": story_ids},
            )
            cluster_by_story: dict[str, list[str]] = {}
            for cr in cluster_rows:
                cluster_by_story.setdefault(str(cr.story_id), []).append(str(cr.article_id))

            # 6. Recommendations — approved only (Page 4)
            rec_rows = await session.execute(
                text(
                    "SELECT id, story_id, audience, recommendation_text, "
                    "       risk_level, confidence_score, needs_human_review "
                    "FROM story_recommendations "
                    "WHERE story_id = ANY(:sids) AND needs_human_review = false "
                    "ORDER BY confidence_score DESC"
                ),
                {"sids": story_ids},
            )
            recs_by_story: dict[str, list[dict[str, Any]]] = {}
            for rr in rec_rows:
                sid = str(rr.story_id)
                recs_by_story.setdefault(sid, []).append(
                    {
                        "id": str(rr.id),
                        "audience": rr.audience or "",
                        "recommendation_text": rr.recommendation_text or "",
                        "risk_level": rr.risk_level or "low",
                        "confidence_score": float(rr.confidence_score or 0),
                        "needs_human_review": bool(rr.needs_human_review),
                    }
                )

        # 7. Assemble payloads
        payloads = []
        for s in stories:
            sid = str(s.id)
            insight_d = insights.get(sid)
            payloads.append(
                {
                    "id": sid,
                    "title": s.title or "",
                    "status": s.status or "active",
                    "risk_level": s.risk_level or "low",
                    "primary_entity_id": entity_id,
                    "entity_name": entity_name,
                    "article_count": int(s.article_count or 0),
                    "articles": articles_by_story.get(sid, []),
                    "insight": insight_d,
                    "cluster_member_ids": cluster_by_story.get(sid, []),
                    "recommendations": recs_by_story.get(sid, []),
                    "updated_at": s.updated_at.isoformat() if s.updated_at else "",
                }
            )

        # 8. Write to Redis
        feed_key = f"{_FEED_KEY_PREFIX}{entity_id}"
        tracked_key = f"{_TRACKED_KEY_PREFIX}{entity_id}"
        payload_bytes = json.dumps(payloads, default=str).encode()

        await redis.set(feed_key, payload_bytes, ex=settings.feed_cache_ttl)
        # Mark entity as tracked (TTL = 10× feed TTL — rebuilt on every update)
        await redis.set(tracked_key, b"1", ex=settings.feed_cache_ttl * 10)

        logger.info(
            "build_feed_cache.done",
            entity_id=entity_id,
            stories=len(payloads),
            bytes=len(payload_bytes),
        )
        return len(payloads)

    finally:
        await redis.aclose()
        await engine.dispose()


@app.task(
    name="tasks.search.build_feed_cache.run",
    queue="ingestion",
    bind=False,
)
def run(*, entity_id: str) -> dict[str, Any]:
    """Build / rebuild the feed cache for *entity_id*."""
    settings = CacheSettings()
    if not settings.database_url:
        logger.warning("build_feed_cache.no_database_url", entity_id=entity_id)
        return {"status": "no_database_url"}
    try:
        count = asyncio.run(_build_payload(entity_id, settings))
        return {"status": "ok", "entity_id": entity_id, "stories": count}
    except Exception as exc:
        logger.error("build_feed_cache.failed", entity_id=entity_id, error=str(exc))
        raise
