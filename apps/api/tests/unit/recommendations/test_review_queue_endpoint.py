"""Unit tests: review queue endpoints — RBAC, approve/reject, audit_log writes.

Uses create_app() so error handlers are registered, then overrides dependencies.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.container import get_cache_gateway, get_db_session
from app.core.security_deps import get_current_user
from app.domain.entities import User
from app.main import create_app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeCache:
    async def get(self, k: str) -> bytes | None:
        return None

    async def set(self, k: str, v: bytes, ttl_seconds: int = 300) -> None:
        pass

    async def delete(self, k: str) -> None:
        pass

    async def ping(self) -> bool:
        return True


def _make_user(role: str = "admin") -> User:
    return User(
        id="reviewer-1",
        workspace_id="ws-1",
        email="admin@example.com",
        role=role,
        hashed_password="",
    )


@contextmanager
def _make_client(user: User, session_execute_side_effects: list[Any] | None = None) -> TestClient:  # type: ignore[misc]
    app = create_app()
    mock_session = AsyncMock()

    if session_execute_side_effects is not None:
        mock_session.execute = AsyncMock(side_effect=session_execute_side_effects)
    else:
        empty = MagicMock()
        empty.__iter__ = MagicMock(return_value=iter([]))
        mock_session.execute = AsyncMock(return_value=empty)

    async def _fake_session():  # type: ignore[no-untyped-def]
        yield mock_session

    app.dependency_overrides[get_db_session] = _fake_session
    app.dependency_overrides[get_cache_gateway] = lambda: _FakeCache()
    app.dependency_overrides[get_current_user] = lambda: user

    yield TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# GET /admin/recommendations/pending-review
# ---------------------------------------------------------------------------

def test_list_pending_requires_admin() -> None:
    """Viewer cannot access the pending review queue."""
    with _make_client(_make_user("viewer")) as client:
        resp = client.get("/api/v1/admin/recommendations/pending-review")
    assert resp.status_code == 403


def test_analyst_cannot_see_pending_queue() -> None:
    """Analyst role is below admin — also forbidden."""
    with _make_client(_make_user("analyst")) as client:
        resp = client.get("/api/v1/admin/recommendations/pending-review")
    assert resp.status_code == 403


def test_list_pending_returns_results_for_admin() -> None:
    row = MagicMock()
    row.id = "rec-1"
    row.story_id = "story-1"
    row.audience = "pr"
    row.recommendation_text = "Issue a statement"
    row.risk_level = "high"
    row.confidence_score = 0.42
    row.generated_at = datetime(2026, 7, 16, tzinfo=UTC)

    mock_result = MagicMock()
    mock_result.__iter__ = MagicMock(return_value=iter([row]))

    with _make_client(_make_user("admin"), session_execute_side_effects=[mock_result]) as client:
        resp = client.get("/api/v1/admin/recommendations/pending-review")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == "rec-1"
    assert data[0]["confidence_score"] == pytest.approx(0.42)


def test_list_pending_empty_when_queue_clear() -> None:
    empty = MagicMock()
    empty.__iter__ = MagicMock(return_value=iter([]))

    with _make_client(_make_user("admin"), session_execute_side_effects=[empty]) as client:
        resp = client.get("/api/v1/admin/recommendations/pending-review")

    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# POST approve
# ---------------------------------------------------------------------------

def test_approve_calls_update_and_audit() -> None:
    approve_row = MagicMock()
    approve_row.id = "rec-1"
    approve_row.story_id = "story-1"
    approve_result = MagicMock()
    approve_result.first = MagicMock(return_value=approve_row)

    empty = MagicMock()
    empty.first = MagicMock(return_value=None)

    effects = [approve_result, empty, empty]  # UPDATE + INSERT workspace + INSERT audit

    with _make_client(_make_user("admin"), session_execute_side_effects=effects) as client:
        resp = client.post("/api/v1/admin/recommendations/rec-1/approve")

    assert resp.status_code == 200
    data = resp.json()
    assert data["action"] == "approved"
    assert data["id"] == "rec-1"
    assert "audit_log_id" in data


def test_approve_404_when_not_found() -> None:
    not_found = MagicMock()
    not_found.first = MagicMock(return_value=None)

    with _make_client(_make_user("admin"), session_execute_side_effects=[not_found]) as client:
        resp = client.post("/api/v1/admin/recommendations/ghost-id/approve")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST reject
# ---------------------------------------------------------------------------

def test_reject_deletes_and_audits() -> None:
    delete_row = MagicMock()
    delete_row.id = "rec-2"
    delete_result = MagicMock()
    delete_result.first = MagicMock(return_value=delete_row)

    empty = MagicMock()
    empty.first = MagicMock(return_value=None)

    effects = [delete_result, empty, empty]

    with _make_client(_make_user("admin"), session_execute_side_effects=effects) as client:
        resp = client.post("/api/v1/admin/recommendations/rec-2/reject")

    assert resp.status_code == 200
    data = resp.json()
    assert data["action"] == "rejected"
    assert data["id"] == "rec-2"


def test_reject_404_when_not_found() -> None:
    not_found = MagicMock()
    not_found.first = MagicMock(return_value=None)

    with _make_client(_make_user("admin"), session_execute_side_effects=[not_found]) as client:
        resp = client.post("/api/v1/admin/recommendations/ghost/reject")

    assert resp.status_code == 404
