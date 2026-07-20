from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import StoryInsight
from app.infrastructure.db.models.story_insight import StoryInsightModel


def _to_domain(row: StoryInsightModel) -> StoryInsight:
    return StoryInsight(
        id=row.id,
        story_id=row.story_id,
        what_happened=row.what_happened,
        why_happened=row.why_happened,
        generated_at=row.generated_at,
        model_used=row.model_used,
        token_cost=row.token_cost,
    )


def _to_model(entity: StoryInsight) -> StoryInsightModel:
    return StoryInsightModel(
        id=entity.id,
        story_id=entity.story_id,
        what_happened=entity.what_happened,
        why_happened=entity.why_happened,
        generated_at=entity.generated_at,
        model_used=entity.model_used,
        token_cost=entity.token_cost,
    )


class SqlAlchemyStoryInsightRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_story_id(self, story_id: str) -> StoryInsight | None:
        stmt = (
            select(StoryInsightModel)
            .where(StoryInsightModel.story_id == story_id)
            .order_by(StoryInsightModel.generated_at.desc())
            .limit(1)
        )
        result = await self._session.scalar(stmt)
        return _to_domain(result) if result is not None else None

    async def save(self, insight: StoryInsight) -> StoryInsight:
        existing = await self._session.get(StoryInsightModel, insight.id)
        if existing is None:
            row = _to_model(insight)
            self._session.add(row)
        else:
            existing.what_happened = insight.what_happened
            existing.why_happened = insight.why_happened
            existing.model_used = insight.model_used
            existing.token_cost = insight.token_cost
            row = existing
        await self._session.flush()
        await self._session.refresh(row)
        return _to_domain(row)
