"""Internal debug endpoint: nearest-neighbour similarity search.

GET /api/v1/internal/similarity/{article_id}?k=10
  Given an article id whose embedding is already stored, returns the top-K
  most similar articles by cosine distance using the HNSW index.

Guarded by Role.admin — not part of the public API surface.
Used during development to validate embedding quality before Phase 15
builds story clustering on top.
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.container import get_db_session
from app.core.security_deps import require_role
from app.domain.value_objects.role import Role

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/internal", tags=["internal"])


class SimilarArticle(BaseModel):
    id: str
    headline: str | None
    source_id: str | None
    cosine_distance: float


@router.get("/similarity/{article_id}", response_model=list[SimilarArticle])
async def nearest_neighbors(
    article_id: str,
    k: Annotated[int, Query(ge=1, le=50)] = 10,
    session: Annotated[AsyncSession, Depends(get_db_session)] = ...,  # type: ignore[assignment]
    _: Annotated[object, Depends(require_role(Role.admin))] = ...,  # type: ignore[assignment]
) -> list[SimilarArticle]:
    """Return the *k* nearest articles to *article_id* by cosine similarity.

    Uses the HNSW index (``vector_cosine_ops``) so the query is fast even on
    large tables.  The source article itself is excluded from results.
    """
    from sqlalchemy import text

    # Fetch the query vector
    row = await session.execute(
        text("SELECT embedding FROM articles WHERE id = :id"),
        {"id": article_id},
    )
    result = row.first()
    if result is None:
        raise HTTPException(status_code=404, detail="Article not found")
    if result[0] is None:
        raise HTTPException(status_code=422, detail="Article has no embedding yet")

    embedding = result[0]

    # pgvector operator <=> is cosine distance
    neighbors = await session.execute(
        text(
            """
            SELECT id, headline, source_id,
                   embedding <=> :vec::vector AS cosine_distance
            FROM articles
            WHERE id != :article_id
              AND embedding IS NOT NULL
            ORDER BY embedding <=> :vec::vector
            LIMIT :k
            """
        ),
        {"vec": str(list(embedding)), "article_id": article_id, "k": k},
    )

    return [
        SimilarArticle(
            id=str(r.id),
            headline=r.headline,
            source_id=str(r.source_id) if r.source_id else None,
            cosine_distance=float(r.cosine_distance),
        )
        for r in neighbors
    ]
