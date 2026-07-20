"""NLP task: normalize one article (HTML strip, language detection).

Thin Celery wrapper around
app.application.use_cases.pipeline.normalize.normalize_article
(the pure function lives in apps/api and is imported here via PYTHONPATH).

Updates articles.clean_content and articles.language in-place.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
from pydantic_settings import BaseSettings, SettingsConfigDict

from workers.celery_app import app

logger = structlog.get_logger(__name__)


class NlpSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = ""


def _normalize_article_pure(raw_content: str) -> tuple[str, str]:
    """Import and call the pure normalization logic."""
    import re
    import unicodedata

    from bs4 import BeautifulSoup  # type: ignore[import-untyped]
    from langdetect import DetectorFactory, detect  # type: ignore[import-untyped]

    DetectorFactory.seed = 0

    soup = BeautifulSoup(raw_content, "lxml")
    plain: str = soup.get_text(separator=" ")

    plain = unicodedata.normalize("NFKC", plain)
    plain = re.sub(r"[ \t\r\f\v]+", " ", plain)
    plain = re.sub(r"\n{3,}", "\n\n", plain)
    clean = plain.strip()

    lang = "en"
    if clean:
        try:
            lang = str(detect(clean[:2000]))
        except Exception:
            lang = "en"

    return clean, lang


async def _run_normalize(article_id: str, database_url: str) -> dict[str, Any]:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    engine = create_async_engine(database_url, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with factory() as session, session.begin():
        row = await session.execute(
            text("SELECT raw_content FROM articles WHERE id = :id"),
            {"id": article_id},
        )
        result = row.first()
        if result is None:
            logger.warning("nlp.normalize.article_not_found", article_id=article_id)
            await engine.dispose()
            return {"status": "not_found"}

        raw_content: str = result[0] or ""
        clean, lang = _normalize_article_pure(raw_content)

        await session.execute(
            text(
                "UPDATE articles SET clean_content = :clean, language = :lang "
                "WHERE id = :id"
            ),
            {"clean": clean, "lang": lang, "id": article_id},
        )

    await engine.dispose()
    logger.info(
        "nlp.normalize.done",
        article_id=article_id,
        language=lang,
        clean_len=len(clean),
    )
    return {"status": "ok", "language": lang, "clean_len": len(clean)}


@app.task(
    name="tasks.nlp.normalize.run",
    queue="nlp",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def run(self: object, *, article_id: str) -> dict[str, Any]:  # type: ignore[misc]
    """Normalize article *article_id*: strip HTML, detect language, persist."""
    settings = NlpSettings()
    if not settings.database_url:
        logger.warning("nlp.normalize.no_database_url", article_id=article_id)
        return {"status": "no_database_url"}

    try:
        return asyncio.run(_run_normalize(article_id, settings.database_url))
    except Exception as exc:
        logger.error("nlp.normalize.failed", article_id=article_id, error=str(exc))
        raise
