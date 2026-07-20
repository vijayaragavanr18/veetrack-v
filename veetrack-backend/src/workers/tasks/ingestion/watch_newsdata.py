"""Celery Beat task: pull NewsData.io articles for a keyword/entity on a schedule.

Each invocation:
  1. Acquires a rate-limit token from the Redis bucket for this source.
  2. Calls NewsData.io /news/search since the last recorded pull window.
  3. Persists raw articles to the `articles` table (dedup via external_id).
  4. Updates the `api_usage_log` row for this source + window.

Normalization (clean_content, embeddings, etc.) happens in Phase 11.
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from pydantic_settings import BaseSettings, SettingsConfigDict

from workers.celery_app import app, worker_settings
from workers.connectors.base import CircuitOpen, RateLimitExceeded, RedisRateLimiter
from workers.connectors.newsdata import NewsDataClient, RawArticle

logger = structlog.get_logger(__name__)

# How far back to look on the first pull (no prior window recorded).
_DEFAULT_LOOKBACK_HOURS = 24


class IngestionSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = ""
    newsdata_api_key: str = ""
    newsdata_calls_per_minute: int = 10


def _make_dedup_hash(external_id: str, source_id: str) -> str:
    return hashlib.sha256(f"{source_id}:{external_id}".encode()).hexdigest()


async def _run_pull(
    source_id: str,
    query: str,
    settings: IngestionSettings,
) -> dict[str, Any]:
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    redis_client: Redis = Redis.from_url(  # type: ignore[type-arg]
        worker_settings.redis_url, decode_responses=False
    )
    limiter = RedisRateLimiter(
        redis_client,
        source_id,
        settings.newsdata_calls_per_minute,
    )
    client = NewsDataClient(settings.newsdata_api_key, source_id, limiter)

    since = datetime.now(UTC) - timedelta(hours=_DEFAULT_LOOKBACK_HOURS)

    articles = await client.fetch(query, since)

    if not articles:
        await redis_client.aclose()
        return {"saved": 0, "skipped": 0}

    engine = create_async_engine(settings.database_url, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    saved = 0
    skipped = 0
    new_article_ids: list[str] = []
    now = datetime.now(UTC)
    window_start = now.replace(second=0, microsecond=0)

    async with factory() as session, session.begin():
        from sqlalchemy import select, text
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        # Import models inline so Celery doesn't need to resolve the full app layer
        from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text
        from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

        # Resolve article table via raw SQL to avoid importing API models
        for article in articles:
            dedup_hash = _make_dedup_hash(article.external_id, source_id)
            # Check for existing article
            result = await session.execute(
                text("SELECT id FROM articles WHERE dedup_hash = :h"),
                {"h": dedup_hash},
            )
            if result.first() is not None:
                skipped += 1
                continue

            article_id = str(uuid.uuid4())
            await session.execute(
                text(
                    """
                    INSERT INTO articles
                        (id, source_id, external_id, url, headline, hero_image_url,
                         publisher, published_at, raw_content, clean_content,
                         language, sentiment_label, sentiment_score, dedup_hash, ingested_at)
                    VALUES
                        (:id, :source_id, :external_id, :url, :headline, :hero_image_url,
                         :publisher, :published_at, :raw_content, :clean_content,
                         :language, :sentiment_label, :sentiment_score, :dedup_hash, :ingested_at)
                    """
                ),
                {
                    "id": article_id,
                    "source_id": source_id,
                    "external_id": article.external_id,
                    "url": article.url,
                    "headline": article.headline,
                    "hero_image_url": article.hero_image_url,
                    "publisher": article.publisher,
                    "published_at": article.published_at,
                    "raw_content": article.raw_content,
                    "clean_content": "",
                    "language": article.language,
                    "sentiment_label": "neutral",
                    "sentiment_score": 0.0,
                    "dedup_hash": dedup_hash,
                    "ingested_at": now,
                },
            )
            new_article_ids.append(article_id)
            saved += 1

        # Upsert api_usage_log
        existing = await session.execute(
            text(
                "SELECT id, calls_made FROM api_usage_log "
                "WHERE source_id = :sid AND window_start = :ws"
            ),
            {"sid": source_id, "ws": window_start},
        )
        row = existing.first()
        if row is None:
            await session.execute(
                text(
                    """
                    INSERT INTO api_usage_log (id, source_id, calls_made, quota_limit, window_start)
                    VALUES (:id, :source_id, :calls_made, :quota_limit, :window_start)
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "source_id": source_id,
                    "calls_made": 1,
                    "quota_limit": settings.newsdata_calls_per_minute,
                    "window_start": window_start,
                },
            )
        else:
            await session.execute(
                text(
                    "UPDATE api_usage_log SET calls_made = calls_made + 1 "
                    "WHERE source_id = :sid AND window_start = :ws"
                ),
                {"sid": source_id, "ws": window_start},
            )

    await engine.dispose()
    await redis_client.aclose()

    for aid in new_article_ids:
        from workers.tasks.nlp.pipeline_orchestrator import dispatch_pipeline
        dispatch_pipeline(aid)

    logger.info(
        "ingestion.newsdata.pull_complete",
        source_id=source_id,
        query=query,
        saved=saved,
        skipped=skipped,
    )
    return {"saved": saved, "skipped": skipped}


@app.task(
    name="tasks.ingestion.watch_newsdata.run",
    queue="ingestion",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def run(self: object, *, source_id: str, query: str) -> dict[str, Any]:  # type: ignore[misc]
    """Pull recent NewsData.io articles for *query* and persist to the articles table."""
    settings = IngestionSettings()
    if not settings.newsdata_api_key:
        logger.warning("ingestion.newsdata.no_api_key", source_id=source_id)
        return {"saved": 0, "skipped": 0, "reason": "no_api_key"}
    if not settings.database_url:
        logger.warning("ingestion.newsdata.no_database_url", source_id=source_id)
        return {"saved": 0, "skipped": 0, "reason": "no_database_url"}

    try:
        return asyncio.run(_run_pull(source_id, query, settings))
    except (CircuitOpen, RateLimitExceeded) as exc:
        logger.warning(
            "ingestion.newsdata.rate_limited",
            source_id=source_id,
            reason=str(exc),
        )
        return {"saved": 0, "skipped": 0, "reason": str(exc)}
    except Exception as exc:
        logger.error(
            "ingestion.newsdata.pull_failed",
            source_id=source_id,
            error=str(exc),
        )
        raise
