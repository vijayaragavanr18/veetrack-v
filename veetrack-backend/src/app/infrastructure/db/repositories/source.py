from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import Source
from app.domain.exceptions import NotFoundError
from app.infrastructure.db.models.source import SourceModel


def _to_domain(row: SourceModel) -> Source:
    return Source(
        id=row.id,
        type=row.type,  # type: ignore[arg-type]
        config_json=dict(row.config_json),
        is_active=row.is_active,
        rate_limit_budget=row.rate_limit_budget,
    )


def _to_model(entity: Source) -> SourceModel:
    return SourceModel(
        id=entity.id,
        type=entity.type,
        config_json=entity.config_json,
        is_active=entity.is_active,
        rate_limit_budget=entity.rate_limit_budget,
    )


class SqlAlchemySourceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, source_id: str) -> Source:
        result = await self._session.get(SourceModel, source_id)
        if result is None:
            raise NotFoundError(f"Source {source_id!r} not found")
        return _to_domain(result)

    async def list_active(self) -> list[Source]:
        stmt = select(SourceModel).where(SourceModel.is_active.is_(True))
        rows = await self._session.scalars(stmt)
        return [_to_domain(r) for r in rows]

    async def save(self, source: Source) -> Source:
        existing = await self._session.get(SourceModel, source.id)
        if existing is None:
            row = _to_model(source)
            self._session.add(row)
        else:
            existing.type = source.type
            existing.config_json = source.config_json
            existing.is_active = source.is_active
            existing.rate_limit_budget = source.rate_limit_budget
            row = existing
        await self._session.flush()
        await self._session.refresh(row)
        return _to_domain(row)
