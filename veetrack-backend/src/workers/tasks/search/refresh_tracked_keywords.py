"""Beat task: re-trigger ingestion for all tracked keyword entities every 30 min."""
from __future__ import annotations

import asyncio
from typing import Any

import structlog
from pydantic_settings import BaseSettings, SettingsConfigDict

from workers.celery_app import app

logger = structlog.get_logger(__name__)


class RefreshSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = ""
    redis_url: str = "redis://localhost:6379/0"


async def _run_refresh(settings: RefreshSettings) -> dict[str, Any]:
    from redis.asyncio import Redis

    redis_client: Redis = Redis.from_url(settings.redis_url, decode_responses=False)
    try:
        # Get all tracked keywords from Redis set
        keywords_raw = await redis_client.smembers(b"vt:tracked_keywords")
        keywords = [kw.decode() for kw in keywords_raw]
    finally:
        await redis_client.aclose()

    if not keywords:
        logger.info("refresh_tracked_keywords.no_keywords")
        return {"status": "ok", "refreshed": 0}

    logger.info("refresh_tracked_keywords.starting", count=len(keywords))

    from workers.tasks.ingestion.watch_newsdata import run as newsdata_run

    for kw in keywords[:20]:  # cap at 20 per cycle to avoid overload
        src_id = f"tracked-{kw[:20].replace(' ', '-')}"
        newsdata_run.apply_async(
            kwargs={"source_id": src_id, "query": kw},
            queue="ingestion",
        )

    return {"status": "ok", "refreshed": len(keywords[:20])}


@app.task(name="tasks.search.refresh_tracked_keywords.run", queue="ingestion", bind=False)
def run() -> dict[str, Any]:
    settings = RefreshSettings()
    if not settings.database_url:
        return {"status": "no_database_url"}
    try:
        return asyncio.run(_run_refresh(settings))
    except Exception as exc:
        logger.error("refresh_tracked_keywords.failed", error=str(exc))
        raise
