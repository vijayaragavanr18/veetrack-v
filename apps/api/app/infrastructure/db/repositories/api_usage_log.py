from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import QuotaStatus
from app.infrastructure.db.models.api_usage_log import ApiUsageLogModel


def _to_domain(row: ApiUsageLogModel) -> QuotaStatus:
    return QuotaStatus(
        source_id=row.source_id,
        calls_made=row.calls_made,
        quota_limit=row.quota_limit,
        window_start=row.window_start,
    )


class SqlAlchemyApiUsageLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_current_window(
        self, source_id: str, window_start: str
    ) -> QuotaStatus | None:
        dt = datetime.fromisoformat(window_start)
        stmt = select(ApiUsageLogModel).where(
            ApiUsageLogModel.source_id == source_id,
            ApiUsageLogModel.window_start == dt,
        )
        row = await self._session.scalar(stmt)
        return _to_domain(row) if row is not None else None

    async def upsert(self, status: QuotaStatus) -> QuotaStatus:
        stmt = select(ApiUsageLogModel).where(
            ApiUsageLogModel.source_id == status.source_id,
            ApiUsageLogModel.window_start == status.window_start,
        )
        row = await self._session.scalar(stmt)
        if row is None:
            row = ApiUsageLogModel(
                id=str(uuid.uuid4()),
                source_id=status.source_id,
                calls_made=status.calls_made,
                quota_limit=status.quota_limit,
                window_start=status.window_start,
            )
            self._session.add(row)
        else:
            row.calls_made = status.calls_made
            row.quota_limit = status.quota_limit
        await self._session.flush()
        await self._session.refresh(row)
        return _to_domain(row)

    async def list_by_source(self, source_id: str, limit: int = 10) -> list[QuotaStatus]:
        stmt = (
            select(ApiUsageLogModel)
            .where(ApiUsageLogModel.source_id == source_id)
            .order_by(desc(ApiUsageLogModel.window_start))
            .limit(limit)
        )
        rows = await self._session.scalars(stmt)
        return [_to_domain(r) for r in rows]
