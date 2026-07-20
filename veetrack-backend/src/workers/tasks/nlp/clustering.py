"""Nightly HDBSCAN full re-cluster task.

Pulls embeddings for articles ingested in the recent window (default: 7 days),
runs ReconcileClusters (pure HDBSCAN logic), then executes the merge/split/new-
story operations against the DB and writes audit_log entries.

Also invalidates the Redis centroid cache after reconciliation so the incremental
cluster_article task picks up the corrected centroids on the next run.

Beat schedule entry (already configured in celery_app.py):
  nightly-recluster → tasks.nlp.clustering.full_recluster  (00:30 UTC daily)
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
import structlog
from pydantic_settings import BaseSettings, SettingsConfigDict

from workers.celery_app import app

logger = structlog.get_logger(__name__)

_CENTROIDS_KEY = "vt:centroids"
_SYSTEM_WORKSPACE_ID = "00000000-0000-0000-0000-000000000000"


class ReconcileSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = ""
    redis_url: str = "redis://localhost:6379/0"
    cluster_window_days: int = 7
    hdbscan_min_cluster_size: int = 3
    hdbscan_min_samples: int = 2


async def _run_reconcile(
    database_url: str,
    redis_url: str,
    window_days: int,
    min_cluster_size: int,
    min_samples: int,
) -> dict[str, Any]:
    from redis.asyncio import Redis
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    engine = create_async_engine(database_url, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    redis: Redis = Redis.from_url(redis_url, decode_responses=False)

    cutoff = datetime.now(UTC) - timedelta(days=window_days)

    try:
        async with factory() as session, session.begin():
            # 1. Load recent articles with embeddings
            rows = await session.execute(
                text(
                    "SELECT id, embedding FROM articles "
                    "WHERE embedding IS NOT NULL AND ingested_at >= :cutoff "
                    "ORDER BY ingested_at DESC"
                ),
                {"cutoff": cutoff},
            )
            article_rows = list(rows)
            if not article_rows:
                logger.info("clustering.reconcile.no_articles")
                return {"status": "no_articles"}

            article_ids = [str(r.id) for r in article_rows]
            embeddings = np.array([list(r.embedding) for r in article_rows], dtype=np.float32)

            # 2. Load current story assignments for these articles
            placeholders = ", ".join(f":aid_{i}" for i in range(len(article_ids)))
            params = {f"aid_{i}": aid for i, aid in enumerate(article_ids)}
            assign_rows = await session.execute(
                text(
                    f"SELECT article_id, story_id FROM story_articles "
                    f"WHERE article_id IN ({placeholders})"
                ),
                params,
            )
            article_to_story: dict[str, str] = {
                str(r.article_id): str(r.story_id) for r in assign_rows
            }

            # 3. Load story member counts for active stories in this window
            story_ids_in_window = set(article_to_story.values())
            story_article_counts: dict[str, int] = {}
            if story_ids_in_window:
                sid_placeholders = ", ".join(f":sid_{i}" for i in range(len(story_ids_in_window)))
                sid_params = {f"sid_{i}": sid for i, sid in enumerate(story_ids_in_window)}
                count_rows = await session.execute(
                    text(
                        f"SELECT story_id, COUNT(*) AS cnt FROM story_articles "
                        f"WHERE story_id IN ({sid_placeholders}) GROUP BY story_id"
                    ),
                    sid_params,
                )
                story_article_counts = {str(r.story_id): int(r.cnt) for r in count_rows}

            # 4. Run pure reconciliation logic
            from app.application.use_cases.clustering.reconcile_clusters import ReconcileClusters
            reconciler = ReconcileClusters(
                min_cluster_size=min_cluster_size,
                min_samples=min_samples,
            )
            ops = reconciler.reconcile(
                article_ids=article_ids,
                embeddings=embeddings,
                article_to_story=article_to_story,
                story_article_counts=story_article_counts,
            )

            merge_count = 0
            split_count = 0
            new_count = 0

            # 5. Execute merges
            for merge in ops.merges:
                # Reassign articles from source story to target
                await session.execute(
                    text(
                        "UPDATE story_articles SET story_id = :target "
                        "WHERE story_id = :source"
                    ),
                    {"target": merge.target_story_id, "source": merge.source_story_id},
                )
                # Archive source story
                await session.execute(
                    text(
                        "UPDATE stories SET status = 'archived', updated_at = now() "
                        "WHERE id = :id"
                    ),
                    {"id": merge.source_story_id},
                )
                # Audit log
                await _write_audit(
                    session,
                    action="story.merge",
                    resource_type="story",
                    resource_id=merge.target_story_id,
                    detail={
                        "source_story_id": merge.source_story_id,
                        "articles_moved": len(merge.article_ids),
                    },
                )
                merge_count += 1
                logger.info(
                    "clustering.reconcile.merge",
                    target=merge.target_story_id,
                    source=merge.source_story_id,
                    articles_moved=len(merge.article_ids),
                )

            # 6. Execute splits
            for split in ops.splits:
                primary_entity_id = await _get_primary_entity(session, split.source_story_id)
                new_story_id = str(uuid.uuid4())
                await session.execute(
                    text(
                        "INSERT INTO stories (id, primary_entity_id, title, status, risk_level) "
                        "VALUES (:id, :eid, :title, 'active', 'low')"
                    ),
                    {
                        "id": new_story_id,
                        "eid": primary_entity_id,
                        "title": f"Split from {split.source_story_id[:8]}",
                    },
                )
                for aid in split.article_ids:
                    await session.execute(
                        text(
                            "UPDATE story_articles SET story_id = :new_sid "
                            "WHERE story_id = :old_sid AND article_id = :aid"
                        ),
                        {"new_sid": new_story_id, "old_sid": split.source_story_id, "aid": aid},
                    )
                await _write_audit(
                    session,
                    action="story.split",
                    resource_type="story",
                    resource_id=new_story_id,
                    detail={
                        "source_story_id": split.source_story_id,
                        "articles_split": len(split.article_ids),
                    },
                )
                split_count += 1
                logger.info(
                    "clustering.reconcile.split",
                    source=split.source_story_id,
                    new_story=new_story_id,
                    articles_split=len(split.article_ids),
                )

            # 7. Create new stories
            for new_op in ops.new_stories:
                if not new_op.article_ids:
                    continue
                first_aid = new_op.article_ids[0]
                primary_entity_id = await _get_primary_entity_from_article(session, first_aid)
                headline_row = await session.execute(
                    text("SELECT headline FROM articles WHERE id = :id"),
                    {"id": first_aid},
                )
                headline_result = headline_row.first()
                title = (
                    (headline_result[0] or "")[:200]
                    if headline_result
                    else f"Story {str(uuid.uuid4())[:8]}"
                )
                new_story_id = str(uuid.uuid4())
                await session.execute(
                    text(
                        "INSERT INTO stories (id, primary_entity_id, title, status, risk_level) "
                        "VALUES (:id, :eid, :title, 'active', 'low')"
                    ),
                    {"id": new_story_id, "eid": primary_entity_id, "title": title},
                )
                for aid in new_op.article_ids:
                    await session.execute(
                        text(
                            "INSERT INTO story_articles (story_id, article_id) "
                            "VALUES (:sid, :aid) ON CONFLICT DO NOTHING"
                        ),
                        {"sid": new_story_id, "aid": aid},
                    )
                new_count += 1

            # 8. Invalidate centroid cache — incremental task will rebuild on next run
            await redis.delete(_CENTROIDS_KEY)

        logger.info(
            "clustering.reconcile.done",
            articles=len(article_ids),
            merges=merge_count,
            splits=split_count,
            new_stories=new_count,
            noise=len(ops.noise_article_ids),
        )
        return {
            "status": "ok",
            "articles": len(article_ids),
            "merges": merge_count,
            "splits": split_count,
            "new_stories": new_count,
            "noise": len(ops.noise_article_ids),
        }

    finally:
        await redis.aclose()
        await engine.dispose()


async def _write_audit(
    session: Any,
    action: str,
    resource_type: str,
    resource_id: str,
    detail: dict[str, Any],
) -> None:
    """Insert an audit_log row. Uses the system workspace; no user for automated ops."""
    from sqlalchemy import text

    # Ensure system workspace exists
    await session.execute(
        text(
            "INSERT INTO workspaces (id, name, plan) "
            "VALUES (:id, 'system', 'system') ON CONFLICT DO NOTHING"
        ),
        {"id": _SYSTEM_WORKSPACE_ID},
    )
    await session.execute(
        text(
            "INSERT INTO audit_log (id, workspace_id, user_id, action, resource_type, resource_id) "
            "VALUES (:id, :wid, NULL, :action, :rtype, :rid)"
        ),
        {
            "id": str(uuid.uuid4()),
            "wid": _SYSTEM_WORKSPACE_ID,
            "action": f"{action}:{json.dumps(detail, separators=(',', ':'))}",
            "rtype": resource_type,
            "rid": resource_id,
        },
    )


async def _get_primary_entity(session: Any, story_id: str) -> str:
    from sqlalchemy import text

    row = await session.execute(
        text("SELECT primary_entity_id FROM stories WHERE id = :id"),
        {"id": story_id},
    )
    result = row.first()
    if result:
        return str(result[0])
    return await _ensure_uncategorised_entity(session)


async def _get_primary_entity_from_article(session: Any, article_id: str) -> str:
    from sqlalchemy import text

    row = await session.execute(
        text(
            "SELECT entity_id FROM article_entities "
            "WHERE article_id = :aid ORDER BY relevance_score DESC LIMIT 1"
        ),
        {"aid": article_id},
    )
    result = row.first()
    if result:
        return str(result[0])
    return await _ensure_uncategorised_entity(session)


async def _ensure_uncategorised_entity(session: Any) -> str:
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


@app.task(
    name="tasks.nlp.clustering.full_recluster",
    queue="nlp",
    bind=False,
)
def full_recluster() -> dict[str, Any]:
    """Nightly HDBSCAN re-cluster: merge/split existing stories, create new ones."""
    settings = ReconcileSettings()
    if not settings.database_url:
        logger.warning("clustering.reconcile.no_database_url")
        return {"status": "no_database_url"}
    try:
        return asyncio.run(
            _run_reconcile(
                settings.database_url,
                settings.redis_url,
                settings.cluster_window_days,
                settings.hdbscan_min_cluster_size,
                settings.hdbscan_min_samples,
            )
        )
    except Exception as exc:
        logger.error("clustering.reconcile.failed", error=str(exc))
        raise
