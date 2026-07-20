"""Unit tests: GET /stories/{id}/recommendations — confidence gating + RBAC.

Uses create_app() so error handlers are registered, then overrides get_current_user
and patches the repository classes at the module level for the duration of each request.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.core.container import get_cache_gateway, get_db_session
from app.core.security_deps import get_current_user
from app.domain.entities import User
from app.domain.exceptions import NotFoundError
from app.main import create_app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 7, 16, tzinfo=UTC)


def _make_rec(
    rec_id: str,
    audience: str,
    confidence: float,
    needs_review: bool,
) -> Any:
    from app.domain.entities import StoryRecommendation

    return StoryRecommendation(
        id=rec_id,
        story_id="story-1",
        recommendation_text=f"{audience} action",
        audience=audience,  # type: ignore[arg-type]
        risk_level="medium",
        confidence_score=confidence,
        needs_human_review=needs_review,
        generated_at=_NOW,
    )


def _make_user(role: str = "viewer") -> User:
    return User(
        id="user-1",
        workspace_id="ws-1",
        email="test@example.com",
        role=role,
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


@contextmanager
def _make_client(
    user: User,
    recs: list[Any],
    story_exists: bool = True,
) -> TestClient:  # type: ignore[misc]
    app = create_app()
    mock_session = AsyncMock()

    async def _fake_session():  # type: ignore[no-untyped-def]
        yield mock_session

    app.dependency_overrides[get_db_session] = _fake_session
    app.dependency_overrides[get_cache_gateway] = lambda: _FakeCache()
    app.dependency_overrides[get_current_user] = lambda: user

    mock_story_repo = AsyncMock()
    if story_exists:
        from app.domain.entities import Story

        mock_story_repo.get_by_id = AsyncMock(
            return_value=Story(id="story-1", title="Test")
        )
    else:
        mock_story_repo.get_by_id = AsyncMock(side_effect=NotFoundError("not found"))

    mock_rec_repo = AsyncMock()
    mock_rec_repo.list_by_story_id = AsyncMock(return_value=recs)

    with (
        patch("app.api.v1.stories.SqlAlchemyStoryRepository", return_value=mock_story_repo),
        patch(
            "app.api.v1.stories.SqlAlchemyStoryRecommendationRepository",
            return_value=mock_rec_repo,
        ),
    ):
        client = TestClient(app, raise_server_exceptions=False)
        yield client  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Default view — only approved recommendations
# ---------------------------------------------------------------------------

def test_default_returns_only_approved() -> None:
    recs = [
        _make_rec("r1", "pr", 0.85, False),
        _make_rec("r2", "exec", 0.45, True),
        _make_rec("r3", "marketing", 0.70, False),
    ]
    with _make_client(_make_user("viewer"), recs) as client:
        resp = client.get("/api/v1/stories/story-1/recommendations")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert all(not r["needs_human_review"] for r in data)


def test_default_empty_when_all_pending() -> None:
    recs = [_make_rec("r1", "pr", 0.20, True)]
    with _make_client(_make_user("viewer"), recs) as client:
        resp = client.get("/api/v1/stories/story-1/recommendations")
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# include_pending_review=true — requires analyst+
# ---------------------------------------------------------------------------

def test_analyst_can_see_pending_with_flag() -> None:
    recs = [
        _make_rec("r1", "pr", 0.85, False),
        _make_rec("r2", "exec", 0.45, True),
    ]
    with _make_client(_make_user("analyst"), recs) as client:
        resp = client.get(
            "/api/v1/stories/story-1/recommendations?include_pending_review=true"
        )
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_admin_can_see_pending_with_flag() -> None:
    recs = [_make_rec("r1", "pr", 0.20, True)]
    with _make_client(_make_user("admin"), recs) as client:
        resp = client.get(
            "/api/v1/stories/story-1/recommendations?include_pending_review=true"
        )
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_viewer_forbidden_from_pending_flag() -> None:
    recs = [_make_rec("r1", "pr", 0.20, True)]
    with _make_client(_make_user("viewer"), recs) as client:
        resp = client.get(
            "/api/v1/stories/story-1/recommendations?include_pending_review=true"
        )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Story not found → 404
# ---------------------------------------------------------------------------

def test_404_for_unknown_story() -> None:
    with _make_client(_make_user("viewer"), [], story_exists=False) as client:
        resp = client.get("/api/v1/stories/nonexistent/recommendations")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------

def test_response_schema_fields_present() -> None:
    recs = [_make_rec("r1", "pr", 0.80, False)]
    with _make_client(_make_user("viewer"), recs) as client:
        resp = client.get("/api/v1/stories/story-1/recommendations")
    assert resp.status_code == 200
    item = resp.json()[0]
    for field in ("id", "audience", "recommendation_text", "risk_level",
                  "confidence_score", "needs_human_review", "generated_at"):
        assert field in item
