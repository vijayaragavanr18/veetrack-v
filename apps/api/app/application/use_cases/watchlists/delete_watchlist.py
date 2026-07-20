"""DeleteWatchlist use case — removes a watchlist entry owned by the calling user."""

from __future__ import annotations

from app.domain.exceptions import ForbiddenError, NotFoundError
from app.domain.interfaces.repositories import WatchlistRepository


class DeleteWatchlist:
    def __init__(self, repo: WatchlistRepository) -> None:
        self._repo = repo

    async def execute(
        self,
        watchlist_id: str,
        requesting_user_id: str,
    ) -> None:
        """Delete the watchlist; raise ForbiddenError if not owned by requesting_user_id."""
        watchlist = await self._repo.get_by_id(watchlist_id)
        if watchlist is None:
            raise NotFoundError(f"Watchlist {watchlist_id!r} not found")
        if watchlist.user_id != requesting_user_id:
            raise ForbiddenError("You do not own this watchlist")
        await self._repo.delete(watchlist_id)
