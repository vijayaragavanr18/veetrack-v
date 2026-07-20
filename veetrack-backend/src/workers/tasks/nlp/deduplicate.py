"""NLP task: near-duplicate detection for one article.

Thin Celery wrapper.  Loads the most recent N articles' MinHash signatures
from the DB, queries the LSH index, and if a near-duplicate is found sets
articles.is_duplicate_of = <canonical_id>.

The LSH index is rebuilt in-memory per invocation (stateless workers).
For a production scale-out, move the index to a shared cache — Phase 15+.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
from pydantic_settings import BaseSettings, SettingsConfigDict

from workers.celery_app import app

logger = structlog.get_logger(__name__)

_LOOKBACK_ROWS = 10_000  # how many recent articles to load into the index


class DeduplicateSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = ""
    dedup_lookback_rows: int = _LOOKBACK_ROWS


def _build_minhash(text: str) -> object:
    from datasketch import MinHash  # type: ignore[import-untyped]

    m = MinHash(num_perm=128)
    encoded = text.encode("utf-8", errors="replace")
    k = 5
    if len(encoded) < k:
        m.update(encoded)
    else:
        for i in range(len(encoded) - k + 1):
            m.update(encoded[i : i + k])
    return m


async def _run_deduplicate(
    article_id: str,
    database_url: str,
    lookback_rows: int,
) -> dict[str, Any]:
    from datasketch import MinHash, MinHashLSH  # type: ignore[import-untyped]
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    engine = create_async_engine(database_url, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with factory() as session, session.begin():
        # Fetch target article
        row = await session.execute(
            text("SELECT clean_content FROM articles WHERE id = :id"),
            {"id": article_id},
        )
        result = row.first()
        if result is None:
            logger.warning("nlp.deduplicate.article_not_found", article_id=article_id)
            await engine.dispose()
            return {"status": "not_found"}

        target_text: str = result[0] or ""
        if not target_text.strip():
            logger.info(
                "nlp.deduplicate.skip_empty_content", article_id=article_id
            )
            await engine.dispose()
            return {"status": "skipped_empty"}

        # Build LSH index from recent non-duplicate articles (excluding target)
        corpus = await session.execute(
            text(
                "SELECT id, clean_content FROM articles "
                "WHERE id != :id AND is_duplicate_of IS NULL "
                "AND clean_content != '' "
                "ORDER BY ingested_at DESC "
                "LIMIT :limit"
            ),
            {"id": article_id, "limit": lookback_rows},
        )
        rows = corpus.fetchall()

        lsh: MinHashLSH = MinHashLSH(threshold=0.5, num_perm=128)
        for r_id, r_text in rows:
            if not r_text:
                continue
            m: MinHash = _build_minhash(r_text)  # type: ignore[assignment]
            import contextlib

            with contextlib.suppress(ValueError):
                lsh.insert(r_id, m)

        # Query the index for the target article
        target_minhash: MinHash = _build_minhash(target_text)  # type: ignore[assignment]
        candidates: list[str] = lsh.query(target_minhash)
        duplicate_of: str | None = candidates[0] if candidates else None

        if duplicate_of:
            await session.execute(
                text(
                    "UPDATE articles SET is_duplicate_of = :dup "
                    "WHERE id = :id"
                ),
                {"dup": duplicate_of, "id": article_id},
            )
            logger.info(
                "nlp.deduplicate.flagged",
                article_id=article_id,
                duplicate_of=duplicate_of,
            )
        else:
            logger.info("nlp.deduplicate.unique", article_id=article_id)

    await engine.dispose()
    return {
        "status": "ok",
        "is_duplicate": duplicate_of is not None,
        "duplicate_of": duplicate_of,
    }


@app.task(
    name="tasks.nlp.deduplicate.run",
    queue="nlp",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def run(self: object, *, article_id: str) -> dict[str, Any]:  # type: ignore[misc]
    """Flag article *article_id* as duplicate if a near-match exists."""
    settings = DeduplicateSettings()
    if not settings.database_url:
        logger.warning("nlp.deduplicate.no_database_url", article_id=article_id)
        return {"status": "no_database_url"}

    try:
        return asyncio.run(
            _run_deduplicate(article_id, settings.database_url, settings.dedup_lookback_rows)
        )
    except Exception as exc:
        logger.error("nlp.deduplicate.failed", article_id=article_id, error=str(exc))
        raise
