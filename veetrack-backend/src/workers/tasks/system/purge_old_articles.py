"""System task: delete articles older than 48 hours and trigger cache rebuild.

Beat schedule: every hour at :00
"""
from __future__ import annotations

import asyncio
from typing import Any

import structlog
from pydantic_settings import BaseSettings, SettingsConfigDict

from workers.celery_app import app

logger = structlog.get_logger(__name__)


class PurgeSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = ""
    redis_url: str = "redis://localhost:6379/0"


async def _run_purge(settings: PurgeSettings) -> dict[str, Any]:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from redis.asyncio import Redis

    engine = create_async_engine(settings.database_url, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    redis: Redis = Redis.from_url(settings.redis_url, decode_responses=False)

    try:
        async with factory() as session, session.begin():
            # Get affected entity_ids before delete (for cache invalidation)
            entity_rows = await session.execute(text("""
                SELECT DISTINCT s.primary_entity_id
                FROM articles a
                JOIN story_articles sa ON sa.article_id = a.id
                JOIN stories s ON s.id = sa.story_id
                WHERE a.published_at < NOW() - INTERVAL '48 hours'
            """))
            affected_entities = [str(r[0]) for r in entity_rows]

            # Delete old articles (cascade deletes story_articles, article_entities via FK)
            result = await session.execute(text("""
                DELETE FROM articles WHERE published_at < NOW() - INTERVAL '48 hours'
            """))
            deleted = result.rowcount

            # Invalidate Redis feed caches for affected entities
            if affected_entities:
                keys = [f"vt:feed:{eid}".encode() for eid in affected_entities]
                await redis.delete(*keys)
                # Also clear cold path caches
                cold_keys = await redis.keys(b"vt:cold:*")
                if cold_keys:
                    await redis.delete(*cold_keys)

        logger.info("purge_old_articles.done", deleted=deleted, affected_entities=len(affected_entities))

        # Trigger cache rebuild for affected entities
        if affected_entities:
            from workers.tasks.search.build_feed_cache import run as cache_run

            for eid in affected_entities[:10]:  # cap at 10 to avoid thundering herd
                cache_run.apply_async(kwargs={"entity_id": eid}, queue="ingestion", countdown=5)

        return {"status": "ok", "deleted": deleted, "affected_entities": len(affected_entities)}
    finally:
        await redis.aclose()
        await engine.dispose()


@app.task(name="tasks.system.purge_old_articles.run", queue="ingestion", bind=False)
def run() -> dict[str, Any]:
    settings = PurgeSettings()
    if not settings.database_url:
        return {"status": "no_database_url"}
    try:
        return asyncio.run(_run_purge(settings))
    except Exception as exc:
        logger.error("purge_old_articles.failed", error=str(exc))
        raise
