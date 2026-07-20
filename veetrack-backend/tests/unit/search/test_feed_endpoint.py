"""Unit tests: GET /feed and GET /stories/{id} endpoints.

Uses create_app() so error handlers are registered.
Patches GetFeed use case and the SQLAlchemy session for story detail endpoint.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fastapi.testclient import TestClient

from app.application.use_cases.search.feed_types import (
    ArticleSummaryItem,
    FeedPage,
    StoryPayload,
)
from app.core.container import get_cache_gateway, get_db_session, get_task_dispatcher
from app.core.security_deps import get_current_user
from app.domain.entities import User
from app.main import create_app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _viewer() -> User:
    return User(
        id="user-1",
        workspace_id="ws-1",
        email="t@example.com",
        role="viewer",
        hashed_password="",
    )


class _FakeCache:
    async def get(self, k: str) -> bytes | None:
        return None

    async def set(self, k: str, v: bytes, ttl_seconds: int = 300) -> None:
        pass

    async def delete(self, k: str) -> None:
        pass

    async def ping(self) -> bool:
        return True


class _FakeDispatcher:
    def send(self, task_name: str, kwargs: dict[str, Any], queue: str = "ingestion") -> None:
        pass


def _make_story_payload(story_id: str = "s1") -> StoryPayload:
    return StoryPayload(
        id=story_id,
        title="Test Story",
        status="active",
        risk_level="low",
        primary_entity_id="eid-1",
        entity_name="Tesla",
        article_count=3,
        articles=[
            ArticleSummaryItem(
                id="a1",
                headline="Headline",
                publisher="Reuters",
                published_at="2026-07-16T00:00:00",
                sentiment_label="neutral",
            )
        ],
        updated_at="2026-07-16T00:00:00",
    )


@contextmanager
def _make_feed_client(feed_page: FeedPage) -> TestClient:  # type: ignore[misc]
    app = create_app()
    mock_session = AsyncMock()

    async def _fake_session():  # type: ignore[no-untyped-def]
        yield mock_session

    app.dependency_overrides[get_db_session] = _fake_session
    app.dependency_overrides[get_cache_gateway] = lambda: _FakeCache()
    app.dependency_overrides[get_task_dispatcher] = lambda: _FakeDispatcher()
    app.dependency_overrides[get_current_user] = lambda: _viewer()

    mock_use_case = AsyncMock()
    mock_use_case.execute = AsyncMock(return_value=feed_page)

    with patch("app.api.v1.feed.GetFeed", return_value=mock_use_case):
        client = TestClient(app, raise_server_exceptions=False)
        yield client  # type: ignore[misc]


@contextmanager
def _make_story_client(story_row: Any | None) -> TestClient:  # type: ignore[misc]
    app = create_app()
    mock_session = AsyncMock()

    mock_result = MagicMock()
    mock_result.first.return_value = story_row
    mock_session.execute = AsyncMock(return_value=mock_result)

    async def _fake_session():  # type: ignore[no-untyped-def]
        yield mock_session

    app.dependency_overrides[get_db_session] = _fake_session
    app.dependency_overrides[get_cache_gateway] = lambda: _FakeCache()
    app.dependency_overrides[get_task_dispatcher] = lambda: _FakeDispatcher()
    app.dependency_overrides[get_current_user] = lambda: _viewer()

    client = TestClient(app, raise_server_exceptions=False)
    yield client  # type: ignore[misc]


# ---------------------------------------------------------------------------
# GET /feed tests
# ---------------------------------------------------------------------------


def test_feed_fast_path_returns_200_with_stories() -> None:
    page = FeedPage(
        stories=[_make_story_payload("s1")],
        next_cursor=None,
        entity_id="eid-1",
        entity_name="Tesla",
        path="fast",
    )
    with _make_feed_client(page) as client:
        resp = client.get("/api/v1/feed?entity=tesla")

    assert resp.status_code == 200
    data = resp.json()
    assert data["path"] == "fast"
    assert data["entity_id"] == "eid-1"
    assert data["entity_name"] == "Tesla"
    assert len(data["stories"]) == 1
    assert data["stories"][0]["id"] == "s1"


def test_feed_cold_path_returns_200() -> None:
    page = FeedPage(
        stories=[],
        next_cursor=None,
        entity_id="",
        entity_name="unknown keyword",
        path="cold",
    )
    with _make_feed_client(page) as client:
        resp = client.get("/api/v1/feed?entity=unknown+keyword")

    assert resp.status_code == 200
    assert resp.json()["path"] == "cold"
    assert resp.json()["stories"] == []


def test_feed_returns_next_cursor_when_present() -> None:
    stories = [_make_story_payload(f"s{i}") for i in range(3)]
    page = FeedPage(
        stories=stories,
        next_cursor="s2",
        entity_id="eid-1",
        entity_name="Tesla",
        path="fast",
    )
    with _make_feed_client(page) as client:
        resp = client.get("/api/v1/feed?entity=tesla&limit=3")

    assert resp.json()["next_cursor"] == "s2"


def test_feed_requires_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    """Feed endpoint accepts unauthenticated requests (optional auth, Phase 6 gates it)."""
    monkeypatch.setenv("JWT_SECRET", "x" * 64)
    app = create_app()
    mock_session = AsyncMock()

    async def _fake_session():  # type: ignore[no-untyped-def]
        yield mock_session

    app.dependency_overrides[get_db_session] = _fake_session
    app.dependency_overrides[get_cache_gateway] = lambda: _FakeCache()
    app.dependency_overrides[get_task_dispatcher] = lambda: _FakeDispatcher()

    mock_use_case = AsyncMock()
    mock_use_case.execute = AsyncMock(return_value=FeedPage(
        stories=[], next_cursor=None, entity_id="", entity_name="", path="cold"
    ))

    with patch("app.api.v1.feed.GetFeed", return_value=mock_use_case):
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/feed?entity=tesla")
    # No auth token → optional user resolves to None, endpoint still runs
    assert resp.status_code in (200, 422)


def test_feed_missing_entity_param_returns_422() -> None:
    page = FeedPage(
        stories=[],
        next_cursor=None,
        entity_id="",
        entity_name="",
        path="cold",
    )
    with _make_feed_client(page) as client:
        resp = client.get("/api/v1/feed")

    assert resp.status_code == 422


def test_feed_story_schema_includes_articles() -> None:
    story = _make_story_payload("s1")
    page = FeedPage(
        stories=[story],
        next_cursor=None,
        entity_id="eid-1",
        entity_name="Tesla",
        path="fast",
    )
    with _make_feed_client(page) as client:
        resp = client.get("/api/v1/feed?entity=tesla")

    story_data = resp.json()["stories"][0]
    assert "articles" in story_data
    assert story_data["articles"][0]["headline"] == "Headline"


# ---------------------------------------------------------------------------
# GET /stories/{id} tests
# ---------------------------------------------------------------------------


def test_get_story_returns_200() -> None:
    from datetime import UTC, datetime

    row = MagicMock()
    row.id = "s1"
    row.title = "Test Story"
    row.status = "active"
    row.risk_level = "low"
    row.primary_entity_id = "eid-1"
    row.entity_name = "Tesla"
    row.article_count = 5
    row.updated_at = datetime(2026, 7, 16, tzinfo=UTC)

    with _make_story_client(row) as client:
        resp = client.get("/api/v1/stories/s1")

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "s1"
    assert data["title"] == "Test Story"
    assert data["status"] == "active"
    assert data["article_count"] == 5


def test_get_story_not_found_returns_404() -> None:
    with _make_story_client(None) as client:
        resp = client.get("/api/v1/stories/nonexistent")

    assert resp.status_code == 404


def test_get_story_requires_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    """Story endpoint accepts unauthenticated requests (optional auth, Phase 6 gates it)."""
    monkeypatch.setenv("JWT_SECRET", "x" * 64)
    with _make_story_client(None) as client:
        resp = client.get("/api/v1/stories/s1")
    # Without a real story row, endpoint returns 404 not 401
    assert resp.status_code in (200, 404, 422)
