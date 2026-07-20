"""Feed router — Phase 18: Fast Path / Cold Path story feed.

GET /feed?entity=&cursor=
  Returns paginated StoryPayload list.
  Fast Path: served from Redis in <20ms.
  Cold Path: pgvector + trigram, returns Page-1 only, enqueues background tracking.

GET /stories/{id}
  Single story detail (status, risk level, title, entity).
"""

from __future__ import annotations

from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.use_cases.search.feed_types import (
    FeedPage,
    StoryPayload,
)
from app.application.use_cases.search.get_feed import GetFeed
from app.core.container import get_cache_gateway, get_db_session, get_task_dispatcher
from app.core.security_deps import get_current_user
from app.domain.entities import User
from app.domain.interfaces.services import CacheGateway, TaskDispatcher

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["feed"])

# ---------------------------------------------------------------------------
# Response schemas (Pydantic — for OpenAPI docs)
# ---------------------------------------------------------------------------


class ArticleItem(BaseModel):
    id: str
    headline: str
    publisher: str
    published_at: str
    sentiment_label: str


class InsightSchema(BaseModel):
    what_happened: str
    why_happened: str
    model_used: str


class RecommendationSchema(BaseModel):
    id: str
    audience: str
    recommendation_text: str
    risk_level: str
    confidence_score: float
    needs_human_review: bool


class StorySchema(BaseModel):
    id: str
    title: str
    status: str
    risk_level: str
    primary_entity_id: str
    entity_name: str
    article_count: int
    articles: list[ArticleItem]
    insight: InsightSchema | None
    cluster_member_ids: list[str]
    recommendations: list[RecommendationSchema]
    updated_at: str


class FeedResponse(BaseModel):
    stories: list[StorySchema]
    next_cursor: str | None
    entity_id: str
    entity_name: str
    path: str  # "fast" | "cold"


# ---------------------------------------------------------------------------
# DB query helper (injected into use case)
# ---------------------------------------------------------------------------


def _make_db_query(session: AsyncSession):  # type: ignore[no-untyped-def]
    async def _query(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        result = await session.execute(text(sql), params)
        columns = result.keys()
        return [dict(zip(columns, row, strict=True)) for row in result]

    return _query


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/feed", response_model=FeedResponse)
async def get_feed(
    entity: Annotated[str, Query(min_length=1, max_length=200)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    session: Annotated[AsyncSession, Depends(get_db_session)] = ...,  # type: ignore[assignment]
    cache: Annotated[CacheGateway, Depends(get_cache_gateway)] = ...,  # type: ignore[assignment]
    dispatcher: Annotated[TaskDispatcher, Depends(get_task_dispatcher)] = ...,  # type: ignore[assignment]
    _: Annotated[User, Depends(get_current_user)] = ...,  # type: ignore[assignment]
) -> FeedResponse:
    """Return the story feed for an entity keyword.

    Fast Path: <20ms from Redis when entity is tracked.
    Cold Path: direct DB query + background tracking trigger.
    """
    use_case = GetFeed(
        cache=cache,
        dispatcher=dispatcher,
        db_query=_make_db_query(session),
    )
    page: FeedPage = await use_case.execute(entity, cursor=cursor, limit=limit)
    return FeedResponse(
        stories=[_story_to_schema(s) for s in page.stories],
        next_cursor=page.next_cursor,
        entity_id=page.entity_id,
        entity_name=page.entity_name,
        path=page.path,
    )


@router.get("/stories/{story_id}", response_model=StorySchema)
async def get_story(
    story_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    _: Annotated[User, Depends(get_current_user)],
) -> StorySchema:
    """Return single story detail."""
    row = await session.execute(
        text(
            "SELECT s.id, s.title, s.status, s.risk_level, s.primary_entity_id, "
            "       s.updated_at, e.canonical_name AS entity_name, "
            "       COUNT(sa.article_id) AS article_count "
            "FROM stories s "
            "JOIN entities e ON e.id = s.primary_entity_id "
            "LEFT JOIN story_articles sa ON sa.story_id = s.id "
            "WHERE s.id = :id "
            "GROUP BY s.id, e.canonical_name"
        ),
        {"id": story_id},
    )
    result = row.first()
    if result is None:
        raise HTTPException(status_code=404, detail="Story not found")

    return StorySchema(
        id=str(result.id),
        title=str(result.title or ""),
        status=str(result.status or "active"),
        risk_level=str(result.risk_level or "low"),
        primary_entity_id=str(result.primary_entity_id),
        entity_name=str(result.entity_name or ""),
        article_count=int(result.article_count or 0),
        articles=[],
        insight=None,
        cluster_member_ids=[],
        recommendations=[],
        updated_at=result.updated_at.isoformat() if result.updated_at else "",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _story_to_schema(s: StoryPayload) -> StorySchema:
    return StorySchema(
        id=s.id,
        title=s.title,
        status=s.status,
        risk_level=s.risk_level,
        primary_entity_id=s.primary_entity_id,
        entity_name=s.entity_name,
        article_count=s.article_count,
        articles=[
            ArticleItem(
                id=a.id,
                headline=a.headline,
                publisher=a.publisher,
                published_at=a.published_at,
                sentiment_label=a.sentiment_label,
            )
            for a in s.articles
        ],
        insight=InsightSchema(
            what_happened=s.insight.what_happened,
            why_happened=s.insight.why_happened,
            model_used=s.insight.model_used,
        )
        if s.insight
        else None,
        cluster_member_ids=s.cluster_member_ids,
        recommendations=[
            RecommendationSchema(
                id=r.id,
                audience=r.audience,
                recommendation_text=r.recommendation_text,
                risk_level=r.risk_level,
                confidence_score=r.confidence_score,
                needs_human_review=r.needs_human_review,
            )
            for r in s.recommendations
        ],
        updated_at=s.updated_at,
    )
