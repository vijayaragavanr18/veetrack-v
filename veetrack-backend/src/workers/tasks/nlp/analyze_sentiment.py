"""NLP task: run sentiment analysis on one article.

Pipeline:
  1. Load clean_content from DB.
  2. Run ModernBERT sentiment classification (GPU/CPU).
  3. Write sentiment_label + sentiment_score back to articles row.

Appended to the pipeline orchestrator chain (Phase 13).
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
from pydantic_settings import BaseSettings, SettingsConfigDict

from workers.celery_app import app

logger = structlog.get_logger(__name__)

_DEFAULT_SENTIMENT_MODEL = "tabularisai/multilingual-sentiment-analysis"

# Map five-class model output → three-class label (mirrored from sentiment_service.py)
_LABEL_MAP: dict[str, str] = {
    "very positive": "positive",
    "positive": "positive",
    "neutral": "neutral",
    "negative": "negative",
    "very negative": "negative",
}

_MIN_WORD_COUNT = 5

# Module-level pipeline singleton (loaded once per worker process)
_sentiment_pipeline: Any = None
_sentiment_model_id: str = ""


class SentimentSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = ""
    sentiment_model_id: str = _DEFAULT_SENTIMENT_MODEL
    # Force CPU (-1) by default so sentiment doesn't compete with vLLM for GPU memory.
    # Set SENTIMENT_DEVICE=0 to use GPU when vLLM is not running.
    sentiment_device: int = -1


def _get_pipeline(model_id: str, device: int = -1) -> Any:
    global _sentiment_pipeline, _sentiment_model_id
    if _sentiment_pipeline is None or _sentiment_model_id != model_id:
        from transformers import pipeline  # type: ignore[import-untyped]

        logger.info("analyze_sentiment.loading_model", model_id=model_id, device=device)
        _sentiment_pipeline = pipeline(
            "text-classification",
            model=model_id,
            device=device,
            truncation=True,
            max_length=512,
        )
        _sentiment_model_id = model_id
    return _sentiment_pipeline


def _get_pipeline_from_settings(settings: SentimentSettings) -> Any:
    return _get_pipeline(settings.sentiment_model_id, settings.sentiment_device)


def _classify(pipe: Any, text: str) -> tuple[str, float, bool]:
    """Return (label, score, low_confidence) for *text*."""
    stripped = text.strip()
    if not stripped:
        return "neutral", 0.5, True

    low_confidence = len(stripped.split()) < _MIN_WORD_COUNT
    raw: dict[str, Any] = pipe(stripped)[0]
    raw_label = str(raw.get("label", "neutral")).lower().strip()
    label = _LABEL_MAP.get(raw_label, "neutral")
    score = float(raw.get("score", 0.5))
    return label, score, low_confidence


async def _run_analyze(
    article_id: str, database_url: str, model_id: str, device: int = -1
) -> dict[str, Any]:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    engine = create_async_engine(database_url, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with factory() as session, session.begin():
        row = await session.execute(
            text("SELECT clean_content FROM articles WHERE id = :id"),
            {"id": article_id},
        )
        result = row.first()
        if result is None:
            logger.warning("analyze_sentiment.article_not_found", article_id=article_id)
            await engine.dispose()
            return {"status": "not_found"}

        clean_content: str = result[0] or ""

        # Inference runs synchronously (transformers pipeline is sync)
        pipe = _get_pipeline(model_id, device)
        label, score, low_confidence = _classify(pipe, clean_content[:2048])

        await session.execute(
            text(
                "UPDATE articles SET sentiment_label = :label, sentiment_score = :score "
                "WHERE id = :id"
            ),
            {"label": label, "score": score, "id": article_id},
        )

    await engine.dispose()
    logger.info(
        "analyze_sentiment.done",
        article_id=article_id,
        label=label,
        score=score,
        low_confidence=low_confidence,
    )
    return {"status": "ok", "label": label, "score": score, "low_confidence": low_confidence}


@app.task(
    name="tasks.nlp.analyze_sentiment.run",
    queue="nlp",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def run(self: object, *, article_id: str) -> dict[str, Any]:  # type: ignore[misc]
    """Classify sentiment for article *article_id* and persist the result."""
    settings = SentimentSettings()
    if not settings.database_url:
        logger.warning("analyze_sentiment.no_database_url", article_id=article_id)
        return {"status": "no_database_url"}

    try:
        return asyncio.run(
            _run_analyze(
                article_id,
                settings.database_url,
                settings.sentiment_model_id,
                settings.sentiment_device,
            )
        )
    except Exception as exc:
        logger.error("analyze_sentiment.failed", article_id=article_id, error=str(exc))
        raise
