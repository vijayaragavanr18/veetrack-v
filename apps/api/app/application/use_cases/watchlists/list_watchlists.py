"""ListWatchlists use case — returns all watchlists for a user in a workspace."""

from __future__ import annotations

from app.domain.entities.watchlist import Watchlist
from app.domain.interfaces.repositories import WatchlistRepository


class ListWatchlists:
    def __init__(self, repo: WatchlistRepository) -> None:
        self._repo = repo

    async def execute(self, workspace_id: str, user_id: str) -> list[Watchlist]:
        return await self._repo.list_by_workspace_user(workspace_id, user_id)
