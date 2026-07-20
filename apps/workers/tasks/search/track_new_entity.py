"""Search task: promote an untracked keyword to a tracked entity.

Called by the Cold Path when a keyword has no entity record.
Steps:
  1. Resolve or create entity + alias in DB.
  2. Trigger connector pulls for the keyword.
  3. Trigger build_feed_cache once an entity_id is established.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import structlog
from pydantic_settings import BaseSettings, SettingsConfigDict

from celery_app import app

logger = structlog.get_logger(__name__)


class TrackSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = ""
    redis_url: str = "redis://localhost:6379/0"


async def _run_track(keyword: str, settings: TrackSettings) -> dict[str, Any]:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    engine = create_async_engine(settings.database_url, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    try:
        async with factory() as session, session.begin():
            # 1. Check for existing alias (case-insensitive)
            alias_row = await session.execute(
                text(
                    "SELECT e.id FROM entities e "
                    "JOIN entity_aliases a ON a.entity_id = e.id "
                    "WHERE lower(a.alias_text) = lower(:kw) LIMIT 1"
                ),
                {"kw": keyword},
            )
            existing = alias_row.first()

            if existing:
                entity_id = str(existing[0])
                logger.info("track_new_entity.already_exists", keyword=keyword, entity_id=entity_id)
            else:
                entity_id = str(uuid.uuid4())
                await session.execute(
                    text(
                        "INSERT INTO entities (id, canonical_name, type, metadata_json) "
                        "VALUES (:id, :name, 'topic', '{}') ON CONFLICT DO NOTHING"
                    ),
                    {"id": entity_id, "name": keyword.title()},
                )
                await session.execute(
                    text(
                        "INSERT INTO entity_aliases (id, entity_id, alias_text, alias_type) "
                        "VALUES (:id, :eid, :alias, 'search') ON CONFLICT DO NOTHING"
                    ),
                    {"id": str(uuid.uuid4()), "eid": entity_id, "alias": keyword.lower()},
                )
                logger.info("track_new_entity.created", keyword=keyword, entity_id=entity_id)

        # 2. Trigger connector pulls
        from tasks.ingestion.watch_newsdata import run as newsdata_run

        newsdata_run.apply_async(
            kwargs={"source_id": f"auto-{entity_id[:8]}", "query": keyword},
            queue="ingestion",
        )

        # 3. Schedule cache build (after articles arrive; slight delay acceptable)
        from tasks.search.build_feed_cache import run as cache_run

        cache_run.apply_async(
            kwargs={"entity_id": entity_id},
            queue="ingestion",
            countdown=30,  # allow 30s for ingestion pipeline to run first
        )

        return {"status": "ok", "entity_id": entity_id, "keyword": keyword}

    finally:
        await engine.dispose()


@app.task(
    name="tasks.search.track_new_entity.run",
    queue="ingestion",
    bind=False,
)
def run(*, keyword: str) -> dict[str, Any]:
    """Track *keyword* as a new entity and kick off background pulls."""
    settings = TrackSettings()
    if not settings.database_url:
        logger.warning("track_new_entity.no_database_url", keyword=keyword)
        return {"status": "no_database_url"}
    try:
        return asyncio.run(_run_track(keyword, settings))
    except Exception as exc:
        logger.error("track_new_entity.failed", keyword=keyword, error=str(exc))
        raise
