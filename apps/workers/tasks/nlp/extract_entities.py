"""NLP task: extract + resolve entities for one article.

Pipeline:
  1. Load clean_content from DB.
  2. Run GLiNER NER to extract entity mentions (company / person / topic labels).
  3. Resolve each mention to a canonical entity via alias-lookup-first strategy:
       exact alias → link; fuzzy (trigram ≥ 0.4) → link + add alias; else → create.
  4. Upsert article_entities rows with per-mention relevance scores.

This task is appended to the Phase 11 pipeline orchestrator chain.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from typing import Any

import structlog
from pydantic_settings import BaseSettings, SettingsConfigDict

from celery_app import app

logger = structlog.get_logger(__name__)

# GLiNER labels mapped to our entity types
_NER_LABELS = ["organization", "person", "location", "topic"]
_NER_THRESHOLD = 0.45
_DEFAULT_MODEL = "urchade/gliner_small-v2.1"

# Fuzzy match threshold (trigram Jaccard)
_FUZZY_THRESHOLD = 0.4


class EntitySettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = ""
    gliner_model_id: str = _DEFAULT_MODEL


# Module-level GLiNER model singleton (loaded once per worker process)
_gliner_model: Any = None
_gliner_model_id: str = ""


def _get_gliner(model_id: str) -> Any:
    global _gliner_model, _gliner_model_id
    if _gliner_model is None or _gliner_model_id != model_id:
        from gliner import GLiNER  # type: ignore[import-untyped]
        import torch

        device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info("extract_entities.loading_gliner", model_id=model_id, device=device)
        _gliner_model = GLiNER.from_pretrained(model_id, map_location=device)
        _gliner_model.eval()
        _gliner_model_id = model_id
    return _gliner_model


def _trigram_set(text: str) -> set[str]:
    s = text.strip().lower()
    if len(s) < 3:
        return {s}
    return {s[i : i + 3] for i in range(len(s) - 2)}


def _trigram_sim(a: str, b: str) -> float:
    ta, tb = _trigram_set(a), _trigram_set(b)
    if not ta and not tb:
        return 1.0
    intersection = len(ta & tb)
    union = len(ta | tb)
    return intersection / union if union else 0.0


_LABEL_TO_TYPE = {
    "organization": "company",
    "org": "company",
    "company": "company",
    "person": "person",
    "per": "person",
    "location": "topic",
    "loc": "topic",
    "topic": "topic",
}


async def _resolve_mention(
    session: Any,
    surface: str,
    label: str,
    all_aliases: list[tuple[str, str]],
) -> str:
    """Resolve *surface* to a canonical entity_id, creating one if needed."""
    from sqlalchemy import text

    # 1. Exact alias match
    row = await session.execute(
        text(
            "SELECT e.id FROM entities e "
            "JOIN entity_aliases a ON a.entity_id = e.id "
            "WHERE a.alias_text = :t LIMIT 1"
        ),
        {"t": surface},
    )
    match = row.first()
    if match:
        return str(match[0])

    # Also try normalised lowercase
    surface_lower = surface.strip().lower()
    if surface_lower != surface:
        row = await session.execute(
            text(
                "SELECT e.id FROM entities e "
                "JOIN entity_aliases a ON a.entity_id = e.id "
                "WHERE a.alias_text = :t LIMIT 1"
            ),
            {"t": surface_lower},
        )
        match = row.first()
        if match:
            entity_id = str(match[0])
            # Add the new surface form as alias
            with contextlib.suppress(Exception):
                await session.execute(
                    text(
                        "INSERT INTO entity_aliases (id, entity_id, alias_text, alias_type) "
                        "VALUES (:id, :eid, :t, 'name') ON CONFLICT DO NOTHING"
                    ),
                    {"id": str(uuid.uuid4()), "eid": entity_id, "t": surface},
                )
            return entity_id

    # 2. Fuzzy match against cached alias list
    best_id: str | None = None
    best_score = 0.0
    for alias_text, entity_id in all_aliases:
        score = _trigram_sim(surface, alias_text)
        if score >= _FUZZY_THRESHOLD and score > best_score:
            best_score = score
            best_id = entity_id

    if best_id is not None:
        # Add new alias for future exact lookups
        with contextlib.suppress(Exception):
            await session.execute(
                text(
                    "INSERT INTO entity_aliases (id, entity_id, alias_text, alias_type) "
                    "VALUES (:id, :eid, :t, 'name') ON CONFLICT DO NOTHING"
                ),
                {"id": str(uuid.uuid4()), "eid": best_id, "t": surface},
            )
        return best_id

    # 3. Create new canonical entity + seed alias
    entity_id = str(uuid.uuid4())
    entity_type = _LABEL_TO_TYPE.get(label.lower(), "topic")
    await session.execute(
        text(
            "INSERT INTO entities (id, canonical_name, type, metadata_json) "
            "VALUES (:id, :name, :type, :meta::jsonb)"
        ),
        {"id": entity_id, "name": surface, "type": entity_type, "meta": "{}"},
    )
    await session.execute(
        text(
            "INSERT INTO entity_aliases (id, entity_id, alias_text, alias_type) "
            "VALUES (:id, :eid, :t, 'name') ON CONFLICT DO NOTHING"
        ),
        {"id": str(uuid.uuid4()), "eid": entity_id, "t": surface},
    )
    logger.info(
        "extract_entities.created_entity",
        entity_id=entity_id,
        canonical=surface,
        entity_type=entity_type,
    )
    return entity_id


async def _run_extract(article_id: str, database_url: str, model_id: str) -> dict[str, Any]:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    engine = create_async_engine(database_url, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with factory() as session, session.begin():
        # Load clean_content
        row = await session.execute(
            text("SELECT clean_content FROM articles WHERE id = :id"),
            {"id": article_id},
        )
        result = row.first()
        if result is None:
            logger.warning("extract_entities.article_not_found", article_id=article_id)
            await engine.dispose()
            return {"status": "not_found"}

        clean_content: str = result[0] or ""
        if not clean_content.strip():
            logger.info("extract_entities.skip_empty_content", article_id=article_id)
            await engine.dispose()
            return {"status": "skipped_empty"}

        # Run GLiNER inference (CPU/GPU, sync — run in thread if needed)
        model = _get_gliner(model_id)
        raw_mentions: list[dict[str, Any]] = model.predict_entities(
            clean_content[:4096],  # cap at 4 096 chars to stay within model token budget
            _NER_LABELS,
            threshold=_NER_THRESHOLD,
        )

        if not raw_mentions:
            logger.info("extract_entities.no_mentions", article_id=article_id)
            await engine.dispose()
            return {"status": "ok", "entities": 0}

        # Fetch all aliases once for fuzzy matching (small table — fits in memory)
        alias_rows = await session.execute(
            text("SELECT alias_text, entity_id FROM entity_aliases")
        )
        all_aliases: list[tuple[str, str]] = [
            (r.alias_text, r.entity_id) for r in alias_rows
        ]

        # Deduplicate mentions by surface form; keep highest-scoring mention per surface
        deduped: dict[str, dict[str, Any]] = {}
        for m in raw_mentions:
            surface = str(m.get("text", "")).strip()
            score = float(m.get("score", 0.0))
            if surface and (surface not in deduped or score > deduped[surface]["score"]):
                deduped[surface] = m

        entity_scores: list[tuple[str, float]] = []
        for mention in deduped.values():
            surface = str(mention.get("text", "")).strip()
            label = str(mention.get("label", "topic"))
            score = float(mention.get("score", 0.0))
            entity_id = await _resolve_mention(session, surface, label, all_aliases)
            entity_scores.append((entity_id, score))

        # Upsert article_entities
        for entity_id, score in entity_scores:
            await session.execute(
                text(
                    "INSERT INTO article_entities (article_id, entity_id, relevance_score) "
                    "VALUES (:aid, :eid, :s) "
                    "ON CONFLICT (article_id, entity_id) DO UPDATE SET relevance_score = :s"
                ),
                {"aid": article_id, "eid": entity_id, "s": score},
            )

    await engine.dispose()
    logger.info(
        "extract_entities.done",
        article_id=article_id,
        entities=len(entity_scores),
    )
    return {"status": "ok", "entities": len(entity_scores)}


@app.task(
    name="tasks.nlp.extract_entities.run",
    queue="nlp",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def run(self: object, *, article_id: str) -> dict[str, Any]:  # type: ignore[misc]
    """Extract + resolve entities for article *article_id* and persist article_entities."""
    settings = EntitySettings()
    if not settings.database_url:
        logger.warning("extract_entities.no_database_url", article_id=article_id)
        return {"status": "no_database_url"}

    try:
        return asyncio.run(
            _run_extract(article_id, settings.database_url, settings.gliner_model_id)
        )
    except Exception as exc:
        logger.error("extract_entities.failed", article_id=article_id, error=str(exc))
        raise
