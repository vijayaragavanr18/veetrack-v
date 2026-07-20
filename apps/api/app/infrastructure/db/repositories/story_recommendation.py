from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import StoryRecommendation
from app.infrastructure.db.models.story_recommendation import StoryRecommendationModel


def _to_domain(row: StoryRecommendationModel) -> StoryRecommendation:
    return StoryRecommendation(
        id=row.id,
        story_id=row.story_id,
        recommendation_text=row.recommendation_text,
        audience=row.audience,  # type: ignore[arg-type]
        risk_level=row.risk_level,  # type: ignore[arg-type]
        confidence_score=row.confidence_score,
        needs_human_review=row.needs_human_review,
        generated_at=row.generated_at,
    )


def _to_model(entity: StoryRecommendation) -> StoryRecommendationModel:
    return StoryRecommendationModel(
        id=entity.id,
        story_id=entity.story_id,
        recommendation_text=entity.recommendation_text,
        audience=entity.audience,
        risk_level=entity.risk_level,
        confidence_score=entity.confidence_score,
        needs_human_review=entity.needs_human_review,
        generated_at=entity.generated_at,
    )


class SqlAlchemyStoryRecommendationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_story_id(self, story_id: str) -> list[StoryRecommendation]:
        stmt = (
            select(StoryRecommendationModel)
            .where(StoryRecommendationModel.story_id == story_id)
            .order_by(StoryRecommendationModel.confidence_score.desc())
        )
        rows = await self._session.scalars(stmt)
        return [_to_domain(r) for r in rows]

    async def save(self, recommendation: StoryRecommendation) -> StoryRecommendation:
        existing = await self._session.get(StoryRecommendationModel, recommendation.id)
        if existing is None:
            row = _to_model(recommendation)
            self._session.add(row)
        else:
            existing.recommendation_text = recommendation.recommendation_text
            existing.confidence_score = recommendation.confidence_score
            existing.needs_human_review = recommendation.needs_human_review
            existing.risk_level = recommendation.risk_level
            row = existing
        await self._session.flush()
        await self._session.refresh(row)
        return _to_domain(row)
