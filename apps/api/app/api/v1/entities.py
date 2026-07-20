"""Entities router.

GET /api/v1/entities/search?q=<query>&limit=<n>
  Returns canonical entities whose name or aliases trigram-match *q*.
  Used by the watchlist autocomplete UI.
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.container import get_db_session
from app.infrastructure.db.repositories.entity import SqlAlchemyEntityRepository

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/entities", tags=["entities"])


class EntityResponse(BaseModel):
    id: str
    canonical_name: str
    type: str


@router.get("/search", response_model=list[EntityResponse])
async def search_entities(
    q: Annotated[str, Query(min_length=1, max_length=255)],
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
    session: Annotated[AsyncSession, Depends(get_db_session)] = ...,  # type: ignore[assignment]
) -> list[EntityResponse]:
    """Autocomplete: return canonical entities matching *q* by trigram similarity."""
    repo = SqlAlchemyEntityRepository(session)
    entities = await repo.search_by_name(q, limit=limit)
    return [
        EntityResponse(id=e.id, canonical_name=e.canonical_name, type=e.type)
        for e in entities
    ]
