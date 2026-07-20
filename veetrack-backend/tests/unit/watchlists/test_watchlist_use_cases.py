"""Unit tests for watchlist use cases.

All tests use fake in-memory repositories — no DB, no Docker required.
"""

from __future__ import annotations

import pytest

from app.application.use_cases.watchlists.create_watchlist import (
    CreateWatchlist,
    CreateWatchlistInput,
)
from app.application.use_cases.watchlists.delete_watchlist import DeleteWatchlist
from app.application.use_cases.watchlists.evaluate_alerts import EvaluateAlerts
from app.application.use_cases.watchlists.list_watchlists import ListWatchlists
from app.domain.entities.watchlist import AlertRecord, Watchlist
from app.domain.exceptions import ConflictError, ForbiddenError, NotFoundError

# ---------------------------------------------------------------------------
# Fake repository
# ---------------------------------------------------------------------------


class FakeWatchlistRepository:
    def __init__(self) -> None:
        self._watchlists: dict[str, Watchlist] = {}
        self._alerts: list[AlertRecord] = []

    async def get_by_id(self, watchlist_id: str) -> Watchlist:
        wl = self._watchlists.get(watchlist_id)
        if wl is None:
            raise NotFoundError(f"Watchlist {watchlist_id!r} not found")
        return wl

    async def list_by_workspace_user(
        self,
        workspace_id: str,
        user_id: str,
    ) -> list[Watchlist]:
        return [
            w
            for w in self._watchlists.values()
            if w.workspace_id == workspace_id and w.user_id == user_id
        ]

    async def find_by_entity(
        self,
        workspace_id: str,
        user_id: str,
        entity_id: str,
    ) -> Watchlist | None:
        for w in self._watchlists.values():
            if w.workspace_id == workspace_id and w.user_id == user_id and w.entity_id == entity_id:
                return w
        return None

    async def save(self, watchlist: Watchlist) -> Watchlist:
        existing = await self.find_by_entity(
            watchlist.workspace_id,
            watchlist.user_id,
            watchlist.entity_id,
        )
        if existing is not None and existing.id != watchlist.id:
            raise ConflictError("Watchlist for entity already exists")
        self._watchlists[watchlist.id] = watchlist
        return watchlist

    async def delete(self, watchlist_id: str) -> None:
        if watchlist_id not in self._watchlists:
            raise NotFoundError(f"Watchlist {watchlist_id!r} not found")
        del self._watchlists[watchlist_id]

    async def list_by_entity_across_workspace(
        self,
        entity_id: str,
        workspace_id: str,
    ) -> list[Watchlist]:
        return [
            w
            for w in self._watchlists.values()
            if w.entity_id == entity_id and w.workspace_id == workspace_id
        ]

    async def save_alert(self, alert: AlertRecord) -> AlertRecord:
        self._alerts.append(alert)
        return alert


# ---------------------------------------------------------------------------
# CreateWatchlist
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_watchlist_returns_saved_entry() -> None:
    repo = FakeWatchlistRepository()
    uc = CreateWatchlist(repo)
    inp = CreateWatchlistInput(
        workspace_id="ws1",
        user_id="u1",
        entity_id="e1",
        alert_channels={"websocket": True},
    )
    result = await uc.execute(inp)
    assert result.workspace_id == "ws1"
    assert result.entity_id == "e1"
    assert result.alert_channels == {"websocket": True}


@pytest.mark.asyncio
async def test_create_watchlist_duplicate_raises_conflict() -> None:
    repo = FakeWatchlistRepository()
    uc = CreateWatchlist(repo)
    inp = CreateWatchlistInput(
        workspace_id="ws1",
        user_id="u1",
        entity_id="e1",
        alert_channels={},
    )
    await uc.execute(inp)
    with pytest.raises(ConflictError):
        await uc.execute(inp)


@pytest.mark.asyncio
async def test_create_watchlist_different_users_same_entity_allowed() -> None:
    repo = FakeWatchlistRepository()
    uc = CreateWatchlist(repo)
    await uc.execute(CreateWatchlistInput("ws1", "u1", "e1", {}))
    # Different user_id — should not raise
    result = await uc.execute(CreateWatchlistInput("ws1", "u2", "e1", {}))
    assert result.user_id == "u2"


# ---------------------------------------------------------------------------
# ListWatchlists
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_watchlists_empty_for_new_user() -> None:
    repo = FakeWatchlistRepository()
    result = await ListWatchlists(repo).execute("ws1", "u1")
    assert result == []


@pytest.mark.asyncio
async def test_list_watchlists_returns_only_caller_items() -> None:
    repo = FakeWatchlistRepository()
    create = CreateWatchlist(repo)
    await create.execute(CreateWatchlistInput("ws1", "u1", "e1", {}))
    await create.execute(CreateWatchlistInput("ws1", "u2", "e2", {}))
    result = await ListWatchlists(repo).execute("ws1", "u1")
    assert len(result) == 1
    assert result[0].entity_id == "e1"


# ---------------------------------------------------------------------------
# DeleteWatchlist
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_watchlist_removes_entry() -> None:
    repo = FakeWatchlistRepository()
    created = await CreateWatchlist(repo).execute(CreateWatchlistInput("ws1", "u1", "e1", {}))
    await DeleteWatchlist(repo).execute(created.id, "u1")
    items = await ListWatchlists(repo).execute("ws1", "u1")
    assert items == []


@pytest.mark.asyncio
async def test_delete_watchlist_wrong_owner_raises_forbidden() -> None:
    repo = FakeWatchlistRepository()
    created = await CreateWatchlist(repo).execute(CreateWatchlistInput("ws1", "u1", "e1", {}))
    with pytest.raises(ForbiddenError):
        await DeleteWatchlist(repo).execute(created.id, "u-other")


@pytest.mark.asyncio
async def test_delete_watchlist_not_found_raises() -> None:
    repo = FakeWatchlistRepository()
    with pytest.raises(NotFoundError):
        await DeleteWatchlist(repo).execute("nonexistent", "u1")


# ---------------------------------------------------------------------------
# EvaluateAlerts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evaluate_alerts_low_risk_fires_no_alerts() -> None:
    repo = FakeWatchlistRepository()
    await CreateWatchlist(repo).execute(
        CreateWatchlistInput("ws1", "u1", "e1", {"websocket": True})
    )
    result = await EvaluateAlerts(repo).execute("story1", "e1", "ws1", "low")
    assert result.fired == []
    assert result.skipped_count == 1


@pytest.mark.asyncio
async def test_evaluate_alerts_medium_risk_fires_no_alerts() -> None:
    repo = FakeWatchlistRepository()
    await CreateWatchlist(repo).execute(
        CreateWatchlistInput("ws1", "u1", "e1", {"websocket": True})
    )
    result = await EvaluateAlerts(repo).execute("story1", "e1", "ws1", "medium")
    assert result.fired == []
    assert result.skipped_count == 1


@pytest.mark.asyncio
async def test_evaluate_alerts_high_risk_fires_alert() -> None:
    repo = FakeWatchlistRepository()
    await CreateWatchlist(repo).execute(
        CreateWatchlistInput("ws1", "u1", "e1", {"websocket": True})
    )
    result = await EvaluateAlerts(repo).execute("story1", "e1", "ws1", "high")
    assert len(result.fired) == 1
    assert result.fired[0].story_id == "story1"
    assert result.fired[0].channel == "websocket"


@pytest.mark.asyncio
async def test_evaluate_alerts_critical_risk_fires_alert() -> None:
    repo = FakeWatchlistRepository()
    await CreateWatchlist(repo).execute(
        CreateWatchlistInput("ws1", "u1", "e1", {"websocket": True})
    )
    result = await EvaluateAlerts(repo).execute("story1", "e1", "ws1", "critical")
    assert len(result.fired) == 1


@pytest.mark.asyncio
async def test_evaluate_alerts_disabled_channel_skipped() -> None:
    repo = FakeWatchlistRepository()
    await CreateWatchlist(repo).execute(
        CreateWatchlistInput("ws1", "u1", "e1", {"websocket": False, "email": False})
    )
    result = await EvaluateAlerts(repo).execute("story1", "e1", "ws1", "critical")
    assert result.fired == []


@pytest.mark.asyncio
async def test_evaluate_alerts_multiple_watchers_fan_out() -> None:
    repo = FakeWatchlistRepository()
    create = CreateWatchlist(repo)
    await create.execute(CreateWatchlistInput("ws1", "u1", "e1", {"websocket": True}))
    await create.execute(CreateWatchlistInput("ws1", "u2", "e1", {"websocket": True}))
    result = await EvaluateAlerts(repo).execute("story1", "e1", "ws1", "high")
    assert len(result.fired) == 2


@pytest.mark.asyncio
async def test_evaluate_alerts_no_watchlists_for_entity() -> None:
    repo = FakeWatchlistRepository()
    result = await EvaluateAlerts(repo).execute("story1", "e_unknown", "ws1", "critical")
    assert result.fired == []
    assert result.skipped_count == 0
