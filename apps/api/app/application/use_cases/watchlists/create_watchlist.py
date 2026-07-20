"""CreateWatchlist use case — adds an entity to a user's watch list."""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.entities.watchlist import Watchlist
from app.domain.interfaces.repositories import WatchlistRepository


@dataclass
class CreateWatchlistInput:
    workspace_id: str
    user_id: str
    entity_id: str
    alert_channels: dict[str, object]


class CreateWatchlist:
    def __init__(self, repo: WatchlistRepository) -> None:
        self._repo = repo

    async def execute(self, inp: CreateWatchlistInput) -> Watchlist:
        """Create a new watchlist entry; raises ConflictError if entity already watched."""
        watchlist = Watchlist(
            workspace_id=inp.workspace_id,
            user_id=inp.user_id,
            entity_id=inp.entity_id,
            alert_channels=inp.alert_channels,
        )
        return await self._repo.save(watchlist)
