"""NLP task: assign a newly embedded article to a story cluster (incremental).

Algorithm:
  1. Load the article's embedding from DB.
  2. Fetch active story centroids from Redis cache (key: vt:centroids).
     On cache miss, load from DB and repopulate cache.
  3. Find the best cosine-similarity match among active stories.
  4. If similarity >= threshold → join that story; update centroid running
     average; update Redis cache entry.
  5. Else → create a new story seeded with this article.

Appended to the pipeline orchestrator chain (Phase 15).
"""

from __future__ import annotations

import asyncio
import json
import math
import uuid
from typing import Any

import structlog
from pydantic_settings import BaseSettings, SettingsConfigDict

from workers.celery_app import app

logger = structlog.get_logger(__name__)

# Redis key for the active-story centroid shortlist
_CENTROIDS_KEY = "vt:centroids"
_CENTROIDS_TTL = 3600  # 1 h — refreshed on every write

# Default similarity threshold (can be overridden via env)
_DEFAULT_THRESHOLD = 0.75
# HNSW ef_search: how many candidates to consider during ANN query
# (lower = faster, higher = more accurate)
_DEFAULT_EF_SEARCH = 40


class ClusterSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = ""
    redis_url: str = "redis://localhost:6379/0"
    cluster_similarity_threshold: float = _DEFAULT_THRESHOLD


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _cosine_sim(a: list[float], b: list[float]) -> float:
    a_flt = [float(x) for x in a]
    b_flt = [float(y) for y in b]
    dot = sum(x * y for x, y in zip(a_flt, b_flt, strict=True))
    na = math.sqrt(sum(x * x for x in a_flt))
    nb = math.sqrt(sum(y * y for y in b_flt))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _update_centroid(old: list[float], n: int, new_vec: list[float]) -> list[float]:
    raw = [(c * n + v) / (n + 1) for c, v in zip(old, new_vec, strict=True)]
    norm = math.sqrt(sum(x * x for x in raw))
    if norm == 0.0:
        return raw
    return [x / norm for x in raw]


# ---------------------------------------------------------------------------
# Redis centroid cache helpers
# ---------------------------------------------------------------------------


async def _load_centroids_from_db(session: Any) -> dict[str, dict[str, Any]]:
    """Load story_id → {centroid, count} from DB into a plain dict."""
    from sqlalchemy import text

    rows = await session.execute(
        text(
            "SELECT s.id, s.cluster_centroid, "
            "       COUNT(sa.article_id) AS cnt "
            "FROM stories s "
            "LEFT JOIN story_articles sa ON sa.story_id = s.id "
            "WHERE s.status = 'active' AND s.cluster_centroid IS NOT NULL "
            "GROUP BY s.id, s.cluster_centroid"
        )
    )
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        result[row.id] = {
            "centroid": list(row.cluster_centroid),
            "count": int(row.cnt),
        }
    return result


async def _get_centroids(redis: Any, session: Any) -> dict[str, dict[str, Any]]:
    """Return centroid cache, populating from DB on miss."""
    raw = await redis.get(_CENTROIDS_KEY)
    if raw:
        return json.loads(raw)  # type: ignore[no-any-return]
    centroids = await _load_centroids_from_db(session)
    await redis.set(_CENTROIDS_KEY, json.dumps(centroids).encode(), ex=_CENTROIDS_TTL)
    return centroids


async def _update_centroid_in_cache(
    redis: Any,
    story_id: str,
    new_centroid: list[float],
    new_count: int,
) -> None:
    raw = await redis.get(_CENTROIDS_KEY)
    centroids: dict[str, dict[str, Any]] = json.loads(raw) if raw else {}
    centroids[story_id] = {"centroid": new_centroid, "count": new_count}
    await redis.set(_CENTROIDS_KEY, json.dumps(centroids).encode(), ex=_CENTROIDS_TTL)


# ---------------------------------------------------------------------------
# Core async logic
# ---------------------------------------------------------------------------


async def _run_cluster(
    article_id: str,
    database_url: str,
    redis_url: str,
    threshold: float,
) -> dict[str, Any]:
    from redis.asyncio import Redis
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    engine = create_async_engine(database_url, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    redis: Redis = Redis.from_url(redis_url, decode_responses=False)

    try:
        async with factory() as session, session.begin():
            # 1. Load article embedding + headline
            row = await session.execute(
                text("SELECT embedding, headline FROM articles WHERE id = :id"),
                {"id": article_id},
            )
            result = row.first()
            if result is None:
                logger.warning("cluster_article.article_not_found", article_id=article_id)
                return {"status": "not_found"}
            if result[0] is None:
                logger.info("cluster_article.no_embedding", article_id=article_id)
                return {"status": "skipped_no_embedding"}

            import json
            raw_vec = result[0]
            if isinstance(raw_vec, str):
                article_vec = json.loads(raw_vec)
            else:
                article_vec = list(raw_vec)
            headline: str = result[1] or ""

            # 2. Get active-story centroid cache
            centroids = await _get_centroids(redis, session)

            # 3. Find best match
            best_story_id: str | None = None
            best_sim = 0.0
            for sid, data in centroids.items():
                sim = _cosine_sim(article_vec, data["centroid"])
                if sim > best_sim:
                    best_sim = sim
                    best_story_id = sid

            if best_story_id and best_sim >= threshold:
                # 4a. Join existing story
                story_data = centroids[best_story_id]
                n = story_data["count"]
                new_centroid = _update_centroid(story_data["centroid"], n, article_vec)
                new_count = n + 1

                await session.execute(
                    text(
                        "INSERT INTO story_articles (story_id, article_id) "
                        "VALUES (:sid, :aid) ON CONFLICT DO NOTHING"
                    ),
                    {"sid": best_story_id, "aid": article_id},
                )
                await session.execute(
                    text(
                        "UPDATE stories SET cluster_centroid = CAST(:vec AS vector), "
                        "updated_at = now() WHERE id = :id"
                    ),
                    {"vec": "[" + ",".join(f"{v:.8f}" for v in new_centroid) + "]", "id": best_story_id},
                )
                await _update_centroid_in_cache(redis, best_story_id, new_centroid, new_count)

                # Fetch entity_id for cache invalidation
                ent_row = await session.execute(
                    text("SELECT primary_entity_id FROM stories WHERE id = :id"),
                    {"id": best_story_id},
                )
                ent_result = ent_row.first()
                joined_entity_id = str(ent_result[0]) if ent_result else ""

                logger.info(
                    "cluster_article.joined_story",
                    article_id=article_id,
                    story_id=best_story_id,
                    similarity=round(best_sim, 4),
                )
                # Trigger summary generation when the cluster reaches meaningful depth
                _maybe_trigger_summary(best_story_id, new_count)
                return {
                    "status": "joined",
                    "story_id": best_story_id,
                    "similarity": best_sim,
                    "entity_id": joined_entity_id,
                }

            else:
                # 4b. Create new story
                # Find the primary entity from article_entities (highest relevance_score)
                entity_row = await session.execute(
                    text(
                        "SELECT entity_id FROM article_entities "
                        "WHERE article_id = :aid ORDER BY relevance_score DESC LIMIT 1"
                    ),
                    {"aid": article_id},
                )
                entity_result = entity_row.first()
                primary_entity_id: str
                if entity_result:
                    primary_entity_id = str(entity_result[0])
                else:
                    # Fallback: use or create a generic "uncategorised" entity
                    primary_entity_id = await _ensure_uncategorised_entity(session)

                new_story_id = str(uuid.uuid4())
                title = headline[:200] if headline else f"Story {new_story_id[:8]}"

                await session.execute(
                    text(
                        "INSERT INTO stories (id, primary_entity_id, title, status, "
                        "cluster_centroid, risk_level) "
                        "VALUES (:id, :eid, :title, 'active', CAST(:vec AS vector), 'low')"
                    ),
                    {
                        "id": new_story_id,
                        "eid": primary_entity_id,
                        "title": title,
                        "vec": "[" + ",".join(f"{v:.8f}" for v in article_vec) + "]",
                    },
                )
                await session.execute(
                    text(
                        "INSERT INTO story_articles (story_id, article_id) "
                        "VALUES (:sid, :aid) ON CONFLICT DO NOTHING"
                    ),
                    {"sid": new_story_id, "aid": article_id},
                )

                await _update_centroid_in_cache(redis, new_story_id, article_vec, 1)
                logger.info(
                    "cluster_article.created_story",
                    article_id=article_id,
                    story_id=new_story_id,
                    headline=headline[:80],
                )
                return {
                    "status": "created",
                    "story_id": new_story_id,
                    "entity_id": primary_entity_id,
                }

    finally:
        await redis.aclose()
        await engine.dispose()


async def _ensure_uncategorised_entity(session: Any) -> str:
    """Return the id of the 'uncategorised' catch-all entity, creating it if absent."""
    from sqlalchemy import text

    row = await session.execute(
        text(
            "SELECT e.id FROM entities e "
            "JOIN entity_aliases a ON a.entity_id = e.id "
            "WHERE a.alias_text = 'uncategorised' LIMIT 1"
        )
    )
    existing = row.first()
    if existing:
        return str(existing[0])

    entity_id = str(uuid.uuid4())
    await session.execute(
        text(
            "INSERT INTO entities (id, canonical_name, type, metadata_json) "
            "VALUES (:id, 'Uncategorised', 'topic', '{}') ON CONFLICT DO NOTHING"
        ),
        {"id": entity_id},
    )
    await session.execute(
        text(
            "INSERT INTO entity_aliases (id, entity_id, alias_text, alias_type) "
            "VALUES (:id, :eid, 'uncategorised', 'name') ON CONFLICT DO NOTHING"
        ),
        {"id": str(uuid.uuid4()), "eid": entity_id},
    )
    return entity_id


def _maybe_trigger_summary(story_id: str, member_count: int) -> None:
    """Fire LLM tasks when a story first crosses the depth threshold."""
    from workers.tasks.llm.generate_summary import MIN_ARTICLES_FOR_SUMMARY

    if member_count == MIN_ARTICLES_FOR_SUMMARY:
        from workers.tasks.llm.generate_recommendation import run as generate_recommendation_task
        from workers.tasks.llm.generate_summary import run as generate_summary_task

        generate_summary_task.apply_async(kwargs={"story_id": story_id})
        generate_recommendation_task.apply_async(kwargs={"story_id": story_id})
        logger.info(
            "cluster_article.llm_tasks_triggered",
            story_id=story_id,
            member_count=member_count,
        )


@app.task(
    name="tasks.nlp.cluster_article.run",
    queue="nlp",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def run(self: object, *, article_id: str) -> dict[str, Any]:  # type: ignore[misc]
    """Assign article *article_id* to an existing story or create a new one."""
    settings = ClusterSettings()
    if not settings.database_url:
        logger.warning("cluster_article.no_database_url", article_id=article_id)
        return {"status": "no_database_url"}
    try:
        result = asyncio.run(
            _run_cluster(
                article_id,
                settings.database_url,
                settings.redis_url,
                settings.cluster_similarity_threshold,
            )
        )
        entity_id = result.get("entity_id", "")
        if entity_id and result.get("status") in ("joined", "created"):
            from workers.tasks.search.build_feed_cache import run as cache_run

            cache_run.apply_async(
                kwargs={"entity_id": entity_id},
                queue="ingestion",
            )
        return result
    except Exception as exc:
        logger.error("cluster_article.failed", article_id=article_id, error=str(exc))
        raise
