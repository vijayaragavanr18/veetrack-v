"""Internal debug endpoint: story cluster inspection.

GET /api/v1/internal/stories/{story_id}/cluster
  Returns the story's current centroid and its member articles with metadata.
  Used during threshold tuning and QA before Phase 16.

Guarded by Role.admin — not part of the public API surface.
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.container import get_db_session
from app.core.security_deps import require_role
from app.domain.value_objects.role import Role

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/internal", tags=["internal"])


class ClusterMemberArticle(BaseModel):
    id: str
    headline: str | None
    published_at: str | None
    sentiment_label: str | None
    cosine_distance_to_centroid: float | None


class StoryClusterDebugResponse(BaseModel):
    story_id: str
    title: str
    status: str
    member_count: int
    centroid_dim: int | None
    members: list[ClusterMemberArticle]


@router.get("/stories/{story_id}/cluster", response_model=StoryClusterDebugResponse)
async def get_story_cluster(
    story_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)] = ...,  # type: ignore[assignment]
    _: Annotated[object, Depends(require_role(Role.admin))] = ...,  # type: ignore[assignment]
) -> StoryClusterDebugResponse:
    """Return the story's centroid and member articles ordered by cosine distance."""
    from sqlalchemy import text

    story_row = await session.execute(
        text("SELECT id, title, status, cluster_centroid FROM stories WHERE id = :id"),
        {"id": story_id},
    )
    story = story_row.first()
    if story is None:
        raise HTTPException(status_code=404, detail="Story not found")

    centroid = story.cluster_centroid
    centroid_dim = len(list(centroid)) if centroid is not None else None

    # Fetch member articles, optionally ordered by distance to centroid
    if centroid is not None:
        member_rows = await session.execute(
            text(
                """
                SELECT a.id, a.headline,
                       a.published_at::text AS published_at,
                       a.sentiment_label,
                       a.embedding <=> :vec::vector AS cosine_distance
                FROM story_articles sa
                JOIN articles a ON a.id = sa.article_id
                WHERE sa.story_id = :story_id
                ORDER BY cosine_distance ASC NULLS LAST
                """
            ),
            {"story_id": story_id, "vec": str(list(centroid))},
        )
    else:
        member_rows = await session.execute(
            text(
                """
                SELECT a.id, a.headline,
                       a.published_at::text AS published_at,
                       a.sentiment_label,
                       NULL AS cosine_distance
                FROM story_articles sa
                JOIN articles a ON a.id = sa.article_id
                WHERE sa.story_id = :story_id
                ORDER BY sa.added_at ASC
                """
            ),
            {"story_id": story_id},
        )

    members = [
        ClusterMemberArticle(
            id=str(r.id),
            headline=r.headline,
            published_at=r.published_at,
            sentiment_label=r.sentiment_label,
            cosine_distance_to_centroid=(
                float(r.cosine_distance) if r.cosine_distance is not None else None
            ),
        )
        for r in member_rows
    ]

    return StoryClusterDebugResponse(
        story_id=story_id,
        title=story.title,
        status=story.status,
        member_count=len(members),
        centroid_dim=centroid_dim,
        members=members,
    )
