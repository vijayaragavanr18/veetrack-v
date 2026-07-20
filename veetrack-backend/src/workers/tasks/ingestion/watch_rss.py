"""Celery Beat task: pull RSS/Atom feeds for a source on a schedule.

Each invocation:
  1. Reads feed_urls from the source row's config_json["feed_urls"].
  2. Fetches all configured feeds via RssClient (per-host rate limiting).
  3. Persists new articles to the `articles` table (SHA-256 dedup hash).
  4. Updates the `api_usage_log` row for this source + window.

Normalisation (clean_content, embeddings, etc.) happens in Phase 11.
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
from workers.connectors.base import CircuitOpen, RateLimitExceeded
from workers.connectors.rss import RssClient

logger = structlog.get_logger(__name__)

_DEFAULT_LOOKBACK_HOURS = 24


class RssIngestionSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = ""
    rss_calls_per_minute: int = 30


def _make_dedup_hash(external_id: str, source_id: str) -> str:
    return hashlib.sha256(f"{source_id}:{external_id}".encode()).hexdigest()


async def _run_pull(
    source_id: str,
    feed_urls: list[str],
    settings: RssIngestionSettings,
) -> dict[str, Any]:
    from redis.asyncio import Redis
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    redis_client: Redis = Redis.from_url(  # type: ignore[type-arg]
        worker_settings.redis_url, decode_responses=False
    )
    client = RssClient(
        source_id,
        feed_urls,
        redis_client,
        calls_per_minute=settings.rss_calls_per_minute,
    )

    since = datetime.now(UTC) - timedelta(hours=_DEFAULT_LOOKBACK_HOURS)
    articles = await client.fetch(since)

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
        from sqlalchemy import text as _text
        await session.execute(
            _text("INSERT INTO sources (id, type, config_json, is_active) VALUES (:id, 'rss', '{}', true) ON CONFLICT (id) DO NOTHING"),
            {"id": source_id},
        )
        for article in articles:
            dedup_hash = _make_dedup_hash(article.external_id, source_id)
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
            text("SELECT id FROM api_usage_log WHERE source_id = :sid AND window_start = :ws"),
            {"sid": source_id, "ws": window_start},
        )
        if existing.first() is None:
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
                    "calls_made": len(feed_urls),
                    "quota_limit": settings.rss_calls_per_minute,
                    "window_start": window_start,
                },
            )
        else:
            await session.execute(
                text(
                    "UPDATE api_usage_log SET calls_made = calls_made + :n "
                    "WHERE source_id = :sid AND window_start = :ws"
                ),
                {"n": len(feed_urls), "sid": source_id, "ws": window_start},
            )

    await engine.dispose()
    await redis_client.aclose()

    for aid in new_article_ids:
        from workers.tasks.nlp.pipeline_orchestrator import dispatch_pipeline

        dispatch_pipeline(aid)

    logger.info(
        "ingestion.rss.pull_complete",
        source_id=source_id,
        feeds=len(feed_urls),
        saved=saved,
        skipped=skipped,
    )
    return {"saved": saved, "skipped": skipped}


@app.task(
    name="tasks.ingestion.watch_rss.run",
    queue="ingestion",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def run(self: object, *, source_id: str, feed_urls: list[str]) -> dict[str, Any]:  # type: ignore[misc]
    """Pull RSS/Atom feeds for *source_id* and persist new articles."""
    settings = RssIngestionSettings()
    if not settings.database_url:
        logger.warning("ingestion.rss.no_database_url", source_id=source_id)
        return {"saved": 0, "skipped": 0, "reason": "no_database_url"}
    if not feed_urls:
        logger.warning("ingestion.rss.no_feed_urls", source_id=source_id)
        return {"saved": 0, "skipped": 0, "reason": "no_feed_urls"}

    try:
        return asyncio.run(_run_pull(source_id, feed_urls, settings))
    except (CircuitOpen, RateLimitExceeded) as exc:
        logger.warning(
            "ingestion.rss.rate_limited",
            source_id=source_id,
            reason=str(exc),
        )
        return {"saved": 0, "skipped": 0, "reason": str(exc)}
    except Exception as exc:
        logger.error(
            "ingestion.rss.pull_failed",
            source_id=source_id,
            error=str(exc),
        )
        raise
