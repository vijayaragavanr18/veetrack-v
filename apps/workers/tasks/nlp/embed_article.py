"""NLP task: generate and store embedding for one article.

Pipeline:
  1. Load clean_content from DB.
  2. Run BGE embedding (GPU/CPU).
  3. Write embedding vector back to articles.embedding (pgvector column).

Appended to the pipeline orchestrator chain (Phase 14).
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
from pydantic_settings import BaseSettings, SettingsConfigDict

from celery_app import app

logger = structlog.get_logger(__name__)

REQUIRED_DIM = 1024
_DEFAULT_EMBEDDING_MODEL = "BAAI/bge-large-en-v1.5"

# Module-level model singleton (loaded once per worker process)
_embedding_model: Any = None
_embedding_model_id: str = ""


class EmbeddingSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = ""
    embedding_model_id: str = _DEFAULT_EMBEDDING_MODEL


def _get_model(model_id: str) -> Any:
    global _embedding_model, _embedding_model_id
    if _embedding_model is None or _embedding_model_id != model_id:
        import torch
        from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]

        device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info("embed_article.loading_model", model_id=model_id, device=device)
        model = SentenceTransformer(model_id, device=device)
        model.eval()

        # Fail fast on dimension mismatch
        probe = model.encode(["probe"], normalize_embeddings=True)
        actual_dim = int(probe.shape[1])
        if actual_dim != REQUIRED_DIM:
            raise ValueError(
                f"embed_article: model {model_id!r} produces {actual_dim}-d vectors; "
                f"schema requires {REQUIRED_DIM}."
            )

        _embedding_model = model
        _embedding_model_id = model_id
        logger.info("embed_article.model_loaded", model_id=model_id, dim=actual_dim)
    return _embedding_model


def _embed_text(model: Any, text: str) -> list[float]:
    """Return a normalised REQUIRED_DIM-dimensional vector for *text*."""
    stripped = text.strip()
    if not stripped:
        return [0.0] * REQUIRED_DIM
    vecs = model.encode([stripped], normalize_embeddings=True)
    return [float(v) for v in vecs[0]]


async def _run_embed(article_id: str, database_url: str, model_id: str) -> dict[str, Any]:
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
            logger.warning("embed_article.article_not_found", article_id=article_id)
            await engine.dispose()
            return {"status": "not_found"}

        clean_content: str = result[0] or ""
        if not clean_content.strip():
            logger.info("embed_article.skip_empty_content", article_id=article_id)
            await engine.dispose()
            return {"status": "skipped_empty"}

        model = _get_model(model_id)
        vector = _embed_text(model, clean_content[:8192])

        # pgvector expects a Python list; SQLAlchemy + asyncpg handle the cast
        await session.execute(
            text("UPDATE articles SET embedding = :vec::vector WHERE id = :id"),
            {"vec": str(vector), "id": article_id},
        )

    await engine.dispose()
    logger.info("embed_article.done", article_id=article_id, dim=len(vector))
    return {"status": "ok", "dim": len(vector)}


@app.task(
    name="tasks.nlp.embed_article.run",
    queue="nlp",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def run(self: object, *, article_id: str) -> dict[str, Any]:  # type: ignore[misc]
    """Embed article *article_id* and store the vector in articles.embedding."""
    settings = EmbeddingSettings()
    if not settings.database_url:
        logger.warning("embed_article.no_database_url", article_id=article_id)
        return {"status": "no_database_url"}

    try:
        return asyncio.run(
            _run_embed(article_id, settings.database_url, settings.embedding_model_id)
        )
    except Exception as exc:
        logger.error("embed_article.failed", article_id=article_id, error=str(exc))
        raise
