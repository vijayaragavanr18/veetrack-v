from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import Story
from app.domain.exceptions import NotFoundError
from app.infrastructure.db.models.story import StoryModel


def _to_domain(row: StoryModel) -> Story:
    return Story(
        id=row.id,
        primary_entity_id=row.primary_entity_id,
        title=row.title,
        status=row.status,  # type: ignore[arg-type]
        risk_level=row.risk_level,  # type: ignore[arg-type]
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_model(entity: Story) -> StoryModel:
    return StoryModel(
        id=entity.id,
        primary_entity_id=entity.primary_entity_id,
        title=entity.title,
        status=entity.status,
        risk_level=entity.risk_level,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


class SqlAlchemyStoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, story_id: str) -> Story:
        result = await self._session.get(StoryModel, story_id)
        if result is None:
            raise NotFoundError(f"Story {story_id!r} not found")
        return _to_domain(result)

    async def list_by_entity(
        self,
        entity_id: str,
        cursor: str | None = None,
        limit: int = 20,
    ) -> list[Story]:
        stmt = (
            select(StoryModel)
            .where(StoryModel.primary_entity_id == entity_id)
            .order_by(StoryModel.created_at.desc())
            .limit(limit)
        )
        if cursor is not None:
            stmt = stmt.where(StoryModel.id < cursor)
        rows = await self._session.scalars(stmt)
        return [_to_domain(r) for r in rows]

    async def save(self, story: Story) -> Story:
        existing = await self._session.get(StoryModel, story.id)
        if existing is None:
            row = _to_model(story)
            self._session.add(row)
        else:
            existing.title = story.title
            existing.status = story.status
            existing.risk_level = story.risk_level
            existing.updated_at = story.updated_at
            row = existing
        await self._session.flush()
        await self._session.refresh(row)
        return _to_domain(row)
