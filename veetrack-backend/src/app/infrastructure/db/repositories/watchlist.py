from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.watchlist import AlertRecord, Watchlist
from app.domain.exceptions import ConflictError, NotFoundError
from app.infrastructure.db.models.alert import AlertModel
from app.infrastructure.db.models.watchlist import WatchlistModel


def _watchlist_to_domain(row: WatchlistModel) -> Watchlist:
    return Watchlist(
        id=row.id,
        workspace_id=row.workspace_id,
        user_id=row.user_id,
        entity_id=row.entity_id,
        alert_channels=row.alert_channels_json or {"websocket": True},
    )


def _alert_to_domain(row: AlertModel) -> AlertRecord:
    return AlertRecord(
        id=row.id,
        watchlist_id=row.watchlist_id,
        story_id=row.story_id,
        sent_at=row.sent_at if row.sent_at else datetime.now(UTC),
        channel=row.channel,
        status=row.status,
    )


class SqlAlchemyWatchlistRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, watchlist_id: str) -> Watchlist:
        row = await self._session.get(WatchlistModel, watchlist_id)
        if row is None:
            raise NotFoundError(f"Watchlist {watchlist_id!r} not found")
        return _watchlist_to_domain(row)

    async def list_by_workspace_user(
        self,
        workspace_id: str,
        user_id: str,
    ) -> list[Watchlist]:
        stmt = (
            select(WatchlistModel)
            .where(
                WatchlistModel.workspace_id == workspace_id,
                WatchlistModel.user_id == user_id,
            )
            .order_by(WatchlistModel.id)
        )
        rows = await self._session.scalars(stmt)
        return [_watchlist_to_domain(r) for r in rows]

    async def find_by_entity(
        self,
        workspace_id: str,
        user_id: str,
        entity_id: str,
    ) -> Watchlist | None:
        stmt = select(WatchlistModel).where(
            WatchlistModel.workspace_id == workspace_id,
            WatchlistModel.user_id == user_id,
            WatchlistModel.entity_id == entity_id,
        )
        row = await self._session.scalar(stmt)
        return _watchlist_to_domain(row) if row else None

    async def save(self, watchlist: Watchlist) -> Watchlist:
        existing = await self.find_by_entity(
            watchlist.workspace_id,
            watchlist.user_id,
            watchlist.entity_id,
        )
        if existing is not None and existing.id != watchlist.id:
            raise ConflictError(f"Watchlist for entity {watchlist.entity_id!r} already exists")
        row = await self._session.get(WatchlistModel, watchlist.id)
        if row is None:
            row = WatchlistModel(
                id=watchlist.id,
                workspace_id=watchlist.workspace_id,
                user_id=watchlist.user_id,
                entity_id=watchlist.entity_id,
                alert_channels_json=watchlist.alert_channels,
            )
            self._session.add(row)
        else:
            row.alert_channels_json = watchlist.alert_channels
        await self._session.flush()
        await self._session.refresh(row)
        return _watchlist_to_domain(row)

    async def delete(self, watchlist_id: str) -> None:
        row = await self._session.get(WatchlistModel, watchlist_id)
        if row is None:
            raise NotFoundError(f"Watchlist {watchlist_id!r} not found")
        await self._session.delete(row)
        await self._session.flush()

    async def list_by_entity_across_workspace(
        self,
        entity_id: str,
        workspace_id: str,
    ) -> list[Watchlist]:
        stmt = (
            select(WatchlistModel)
            .where(
                WatchlistModel.entity_id == entity_id,
                WatchlistModel.workspace_id == workspace_id,
            )
            .order_by(WatchlistModel.id)
        )
        rows = await self._session.scalars(stmt)
        return [_watchlist_to_domain(r) for r in rows]

    async def save_alert(self, alert: AlertRecord) -> AlertRecord:
        row = AlertModel(
            id=alert.id,
            watchlist_id=alert.watchlist_id,
            story_id=alert.story_id,
            sent_at=alert.sent_at,
            channel=alert.channel,
            status=alert.status,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return _alert_to_domain(row)
