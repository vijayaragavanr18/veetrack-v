"""Use case: serve the story feed for an entity — Fast Path or Cold Path.

Fast Path (entity already tracked with cached payload):
  - read from CacheGateway only
  - zero NLP/LLM at request time
  - returns full 4-page StoryPayload list

Cold Path (entity unknown or cache miss):
  - pgvector cosine-similarity + Postgres full-text trigram search
  - returns Page-1-level results (articles only, no insight/recs yet)
  - enqueues track_new_entity via TaskDispatcher so next search is Fast Path

Zero infrastructure imports in this module — all I/O is via Protocols.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from typing import Any

import structlog

from app.application.use_cases.search.feed_types import (
    ALIAS_CACHE_TTL,
    COLD_RESULT_CACHE_TTL,
    ArticleSummaryItem,
    FeedPage,
    InsightItem,
    RecommendationItem,
    StoryPayload,
    feed_cache_key,
)
from app.domain.interfaces.services import CacheGateway, TaskDispatcher

_ALIAS_KEY_PREFIX = "vt:alias:"

logger = structlog.get_logger(__name__)

_PAGE_SIZE = 20
_COLD_PATH_ARTICLE_LIMIT = 50  # max articles to pull for cold query
_COLD_PATH_STORY_LIMIT = 10  # cap stories surfaced in cold path


class GetFeed:
    """Serve a paginated story feed.

    Parameters
    ----------
    cache:
        CacheGateway — **the only I/O used in the Fast Path handler**.
        No NLP or LLM service is injected; if this class ever imports one it
        would be an architecture violation.
    dispatcher:
        TaskDispatcher — used by the Cold Path to enqueue background tracking.
    db_query:
        Callable that executes raw SQL against the DB (injected so the use case
        stays infrastructure-free).  Signature:
          async def query(sql, params) -> list[dict]
    """

    def __init__(
        self,
        cache: CacheGateway,
        dispatcher: TaskDispatcher,
        db_query: Any,  # Callable[[str, dict], Awaitable[list[dict]]]
    ) -> None:
        self._cache = cache
        self._dispatcher = dispatcher
        self._db_query = db_query

    async def execute(
        self,
        entity_query: str,
        cursor: str | None = None,
        limit: int = _PAGE_SIZE,
    ) -> FeedPage:
        """Return a feed page for *entity_query*."""
        entity_query = entity_query.strip()

        # 1. Resolve query to entity_id — check alias micro-cache first to avoid
        #    a DB round-trip on every Fast Path request.
        alias_cache_key = f"{_ALIAS_KEY_PREFIX}{entity_query.lower()}"
        alias_cached = await self._cache.get(alias_cache_key)

        entity_id: str | None = None
        entity_name: str = entity_query

        if alias_cached is not None:
            parts = alias_cached.decode().split("\x00", 1)
            entity_id = parts[0] or None
            entity_name = parts[1] if len(parts) > 1 else entity_query
        else:
            entity_rows = await self._db_query(
                """
                SELECT e.id, e.canonical_name
                FROM entities e
                JOIN entity_aliases a ON a.entity_id = e.id
                WHERE lower(a.alias_text) = lower(:q)
                LIMIT 1
                """,
                {"q": entity_query},
            )
            if entity_rows:
                entity_id = str(entity_rows[0]["id"])
                entity_name = str(entity_rows[0]["canonical_name"])
            # Cache the result (even a miss, stored as empty entity_id) so we
            # don't hit the DB again within the TTL window.
            await self._cache.set(
                alias_cache_key,
                f"{entity_id or ''}\x00{entity_name}".encode(),
                ttl_seconds=ALIAS_CACHE_TTL,
            )

        # 2. Fast Path: is this entity tracked with a warmed cache?
        if entity_id is not None:
            cached_raw = await self._cache.get(feed_cache_key(entity_id))
            if cached_raw is not None:
                return self._deserialise_fast_path(
                    cached_raw, entity_id, entity_name, cursor, limit
                )

        # 3. Cold Path — pgvector + full-text query.
        #    Check a short-lived cold-result cache first to suppress thundering-herd
        #    on the first few seconds while the background track task is starting.
        cold_cache_key = f"vt:cold:{entity_query.lower()}:{cursor or ''}:{limit}"
        cold_cached = await self._cache.get(cold_cache_key)
        if cold_cached is not None:
            stories = _deserialise_payloads(cold_cached)
        else:
            logger.info(
                "feed.cold_path",
                entity_query=entity_query,
                entity_id=entity_id,
            )
            stories = await self._cold_query(entity_query, entity_id, cursor, limit)
            if stories:
                await self._cache.set(
                    cold_cache_key,
                    serialise_payloads(stories),
                    ttl_seconds=COLD_RESULT_CACHE_TTL,
                )

        # 4. Enqueue background tracking (idempotent if already in-flight)
        if entity_id is None:
            # unknown keyword → create entity + track
            self._dispatcher.send(
                "tasks.search.track_new_entity.run",
                kwargs={"keyword": entity_query},
                queue="ingestion",
            )
        else:
            # known entity, cache missed → rebuild cache
            self._dispatcher.send(
                "tasks.search.build_feed_cache.run",
                kwargs={"entity_id": entity_id},
                queue="ingestion",
            )

        next_cursor: str | None = None
        if len(stories) == limit:
            next_cursor = stories[-1].id

        return FeedPage(
            stories=stories,
            next_cursor=next_cursor,
            entity_id=entity_id or "",
            entity_name=entity_name,
            path="cold",
        )

    # ------------------------------------------------------------------
    # Fast Path
    # ------------------------------------------------------------------

    def _deserialise_fast_path(
        self,
        raw: bytes,
        entity_id: str,
        entity_name: str,
        cursor: str | None,
        limit: int,
    ) -> FeedPage:
        all_payloads: list[StoryPayload] = _deserialise_payloads(raw)
        # Cursor pagination over the ordered list
        start = 0
        if cursor is not None:
            for i, p in enumerate(all_payloads):
                if p.id == cursor:
                    start = i + 1
                    break
        page = all_payloads[start : start + limit]
        next_cursor = page[-1].id if len(page) == limit else None

        logger.debug(
            "feed.fast_path",
            entity_id=entity_id,
            returned=len(page),
        )
        return FeedPage(
            stories=page,
            next_cursor=next_cursor,
            entity_id=entity_id,
            entity_name=entity_name,
            path="fast",
        )

    # ------------------------------------------------------------------
    # Cold Path
    # ------------------------------------------------------------------

    async def _cold_query(
        self,
        keyword: str,
        entity_id: str | None,
        cursor: str | None,
        limit: int,
    ) -> list[StoryPayload]:
        """Trigram full-text search; returns Page-1 (articles) only."""
        safe_kw = _sanitise(keyword)
        if not safe_kw:
            return []

        if entity_id:
            # Entity known but cache miss — fetch stories by entity_id
            cursor_clause = "AND s.id < :cursor" if cursor else ""
            rows = await self._db_query(
                f"""
                SELECT s.id, s.title, s.status, s.risk_level,
                       s.primary_entity_id, s.updated_at,
                       e.canonical_name AS entity_name,
                       COUNT(sa.article_id) AS article_count
                FROM stories s
                JOIN entities e ON e.id = s.primary_entity_id
                LEFT JOIN story_articles sa ON sa.story_id = s.id
                WHERE s.primary_entity_id = :eid
                  AND s.status = 'active'
                  {cursor_clause}
                GROUP BY s.id, e.canonical_name
                ORDER BY s.updated_at DESC
                LIMIT :lim
                """,
                {"eid": entity_id, "lim": limit, "cursor": cursor or ""},
            )
        else:
            # Keyword not tracked — full-text trigram on articles → aggregate to stories
            cursor_clause = "AND s.id < :cursor" if cursor else ""
            rows = await self._db_query(
                f"""
                SELECT DISTINCT s.id, s.title, s.status, s.risk_level,
                       s.primary_entity_id, s.updated_at,
                       e.canonical_name AS entity_name,
                       COUNT(sa2.article_id) AS article_count
                FROM articles a
                JOIN story_articles sa ON sa.article_id = a.id
                JOIN stories s ON s.id = sa.story_id
                JOIN entities e ON e.id = s.primary_entity_id
                JOIN story_articles sa2 ON sa2.story_id = s.id
                WHERE s.status = 'active'
                  AND (
                    a.headline % :kw
                    OR to_tsvector('english', coalesce(a.clean_content,''))
                       @@ plainto_tsquery('english', :kw)
                  )
                  {cursor_clause}
                GROUP BY s.id, e.canonical_name
                ORDER BY s.updated_at DESC
                LIMIT :lim
                """,
                {"kw": safe_kw, "lim": limit, "cursor": cursor or ""},
            )

        if not rows:
            return []

        story_ids = [str(r["id"]) for r in rows]
        # Load up to 5 articles per story for the Page-1 preview
        article_rows = await self._db_query(
            """
            SELECT a.id, a.headline, a.publisher, a.published_at,
                   a.sentiment_label, sa.story_id
            FROM articles a
            JOIN story_articles sa ON sa.article_id = a.id
            WHERE sa.story_id = ANY(:sids)
            ORDER BY a.published_at DESC
            """,
            {"sids": story_ids},
        )

        articles_by_story: dict[str, list[ArticleSummaryItem]] = {}
        for ar in article_rows:
            sid = str(ar["story_id"])
            if len(articles_by_story.get(sid, [])) < 5:
                articles_by_story.setdefault(sid, []).append(
                    ArticleSummaryItem(
                        id=str(ar["id"]),
                        headline=str(ar["headline"] or ""),
                        publisher=str(ar["publisher"] or ""),
                        published_at=ar["published_at"].isoformat() if ar["published_at"] else "",
                        sentiment_label=str(ar["sentiment_label"] or "neutral"),
                    )
                )

        payloads: list[StoryPayload] = []
        for r in rows:
            sid = str(r["id"])
            payloads.append(
                StoryPayload(
                    id=sid,
                    title=str(r["title"] or ""),
                    status=str(r["status"] or "active"),
                    risk_level=str(r["risk_level"] or "low"),
                    primary_entity_id=str(r["primary_entity_id"]),
                    entity_name=str(r["entity_name"] or keyword),
                    article_count=int(r["article_count"] or 0),
                    articles=articles_by_story.get(sid, []),
                    updated_at=r["updated_at"].isoformat() if r["updated_at"] else "",
                )
            )
        return payloads


# ------------------------------------------------------------------
# Serialisation helpers
# ------------------------------------------------------------------


def _sanitise(text: str) -> str:
    """Strip characters unsafe for use in trigram / tsquery."""
    return re.sub(r"[^\w\s\-]", "", text).strip()[:200]


def serialise_payloads(payloads: list[StoryPayload]) -> bytes:
    return json.dumps([asdict(p) for p in payloads], default=str).encode()


def _deserialise_payloads(raw: bytes) -> list[StoryPayload]:
    items = json.loads(raw)
    result: list[StoryPayload] = []
    for d in items:
        insight = None
        if d.get("insight"):
            insight = InsightItem(**d["insight"])
        recs = [RecommendationItem(**r) for r in (d.get("recommendations") or [])]
        articles = [ArticleSummaryItem(**a) for a in (d.get("articles") or [])]
        result.append(
            StoryPayload(
                id=d["id"],
                title=d["title"],
                status=d["status"],
                risk_level=d["risk_level"],
                primary_entity_id=d["primary_entity_id"],
                entity_name=d["entity_name"],
                article_count=d["article_count"],
                articles=articles,
                insight=insight,
                cluster_member_ids=d.get("cluster_member_ids") or [],
                recommendations=recs,
                updated_at=d.get("updated_at") or "",
            )
        )
    return result
