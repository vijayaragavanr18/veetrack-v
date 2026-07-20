"""Stories router — Phase 17: recommendations endpoint.

GET /stories/{story_id}/recommendations
  - Default (viewer/analyst): returns only approved (needs_human_review=False) recommendations.
  - With ?include_pending_review=true: analyst or admin only — returns all, including flagged.
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.container import get_db_session
from app.core.security_deps import get_current_user
from app.domain.entities import User
from app.domain.exceptions import ForbiddenError, NotFoundError
from app.infrastructure.db.repositories.story import SqlAlchemyStoryRepository
from app.infrastructure.db.repositories.story_recommendation import (
    SqlAlchemyStoryRecommendationRepository,
)

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/stories", tags=["stories"])


class RecommendationResponse(BaseModel):
    id: str
    story_id: str
    audience: str
    recommendation_text: str
    risk_level: str
    confidence_score: float
    needs_human_review: bool
    generated_at: str


@router.get("/{story_id}/recommendations", response_model=list[RecommendationResponse])
async def get_story_recommendations(
    story_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    include_pending_review: Annotated[bool, Query()] = False,
) -> list[RecommendationResponse]:
    """Return recommendations for a story.

    By default only approved (needs_human_review=False) recommendations are returned.
    Pass ``include_pending_review=true`` to see all — requires analyst role or higher.
    """
    # Verify story exists
    story_repo = SqlAlchemyStoryRepository(session)
    try:
        await story_repo.get_by_id(story_id)
    except NotFoundError as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Story not found") from exc

    rec_repo = SqlAlchemyStoryRecommendationRepository(session)
    all_recs = await rec_repo.list_by_story_id(story_id)

    if include_pending_review:
        from app.domain.value_objects.role import Role

        user_role = Role.from_str(current_user.role)
        if user_role < Role.analyst:
            raise ForbiddenError("include_pending_review requires analyst role or higher")
        recs = all_recs
    else:
        recs = [r for r in all_recs if not r.needs_human_review]

    return [
        RecommendationResponse(
            id=r.id,
            story_id=r.story_id,
            audience=r.audience,
            recommendation_text=r.recommendation_text,
            risk_level=r.risk_level,
            confidence_score=r.confidence_score,
            needs_human_review=r.needs_human_review,
            generated_at=r.generated_at.isoformat(),
        )
        for r in recs
    ]
