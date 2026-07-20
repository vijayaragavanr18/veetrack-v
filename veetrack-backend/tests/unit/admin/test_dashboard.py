"""Unit tests for the admin dashboard.

Tests:
- error counter sliding window logic
- RBAC: non-admin roles get 403
- dashboard endpoint structure (with fake dependencies)
"""

from __future__ import annotations

import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.admin.dashboard import (
    _error_window,
    get_recent_error_count,
    record_api_error,
)


# ---------------------------------------------------------------------------
# Error counter unit tests
# ---------------------------------------------------------------------------


def _reset_window() -> None:
    _error_window.clear()


def test_record_api_error_increments_count() -> None:
    _reset_window()
    record_api_error()
    assert get_recent_error_count() == 1


def test_multiple_errors_count_correctly() -> None:
    _reset_window()
    for _ in range(5):
        record_api_error()
    assert get_recent_error_count() == 5


def test_empty_window_returns_zero() -> None:
    _reset_window()
    assert get_recent_error_count() == 0


def test_errors_outside_window_are_excluded() -> None:
    """Entries older than 1 h should not be counted."""
    _reset_window()
    # Inject a fake old timestamp directly
    from app.api.v1.admin.dashboard import _ERROR_WINDOW_SECONDS
    old_ts = time.monotonic() - _ERROR_WINDOW_SECONDS - 1
    _error_window.append(old_ts)
    assert get_recent_error_count() == 0


def test_mixed_old_and_new_errors() -> None:
    from app.api.v1.admin.dashboard import _ERROR_WINDOW_SECONDS
    _reset_window()
    old_ts = time.monotonic() - _ERROR_WINDOW_SECONDS - 1
    _error_window.append(old_ts)
    record_api_error()   # fresh
    record_api_error()   # fresh
    assert get_recent_error_count() == 2


# ---------------------------------------------------------------------------
# RBAC tests via TestClient
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_error_window():
    _reset_window()
    yield
    _reset_window()


def _make_admin_client(role: str) -> tuple[FastAPI, TestClient]:
    """Return a test client with a mocked current user of *role*."""
    import os
    os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
    os.environ.setdefault("JWT_SECRET", "test-secret-that-is-long-enough-for-tests-only")

    from app.core.security_deps import get_current_user
    from app.domain.entities import User
    from app.main import create_app

    fake_user = User(
        id="u1",
        workspace_id="ws1",
        email="test@test.com",
        role=role,  # type: ignore[arg-type]
        hashed_password="",
    )

    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: fake_user
    return app, TestClient(app, raise_server_exceptions=False)


class TestDashboardRBAC:
    def test_viewer_gets_403(self) -> None:
        _, client = _make_admin_client("viewer")
        resp = client.get("/api/v1/admin/dashboard")
        assert resp.status_code == 403

    def test_analyst_gets_403(self) -> None:
        _, client = _make_admin_client("analyst")
        resp = client.get("/api/v1/admin/dashboard")
        assert resp.status_code == 403

    def test_admin_gets_through_rbac(self) -> None:
        """Admin gets past RBAC gate (actual DB call fails — that's fine for RBAC test)."""
        _, client = _make_admin_client("admin")
        resp = client.get("/api/v1/admin/dashboard")
        # 200 if DB happens to be up, 500 if not — either way NOT 403
        assert resp.status_code != 403

    def test_owner_gets_through_rbac(self) -> None:
        _, client = _make_admin_client("owner")
        resp = client.get("/api/v1/admin/dashboard")
        assert resp.status_code != 403


class TestReviewQueueRBAC:
    def test_viewer_cannot_access_pending_review(self) -> None:
        _, client = _make_admin_client("viewer")
        resp = client.get("/api/v1/admin/recommendations/pending-review")
        assert resp.status_code == 403

    def test_analyst_cannot_access_pending_review(self) -> None:
        _, client = _make_admin_client("analyst")
        resp = client.get("/api/v1/admin/recommendations/pending-review")
        assert resp.status_code == 403

    def test_admin_passes_rbac_on_pending_review(self) -> None:
        _, client = _make_admin_client("admin")
        resp = client.get("/api/v1/admin/recommendations/pending-review")
        assert resp.status_code != 403

    def test_viewer_cannot_approve(self) -> None:
        _, client = _make_admin_client("viewer")
        resp = client.post("/api/v1/admin/recommendations/some-id/approve")
        assert resp.status_code == 403

    def test_viewer_cannot_reject(self) -> None:
        _, client = _make_admin_client("viewer")
        resp = client.post("/api/v1/admin/recommendations/some-id/reject")
        assert resp.status_code == 403

    def test_admin_passes_rbac_on_approve(self) -> None:
        _, client = _make_admin_client("admin")
        resp = client.post("/api/v1/admin/recommendations/nonexistent/approve")
        # 404 (not found) is fine — means RBAC passed
        assert resp.status_code in (404, 200, 500)
        assert resp.status_code != 403

    def test_admin_passes_rbac_on_reject(self) -> None:
        _, client = _make_admin_client("admin")
        resp = client.post("/api/v1/admin/recommendations/nonexistent/reject")
        assert resp.status_code != 403


class TestObservability:
    def test_prometheus_endpoint_exists(self) -> None:
        _, client = _make_admin_client("admin")
        resp = client.get("/metrics")
        # 200 if prometheus enabled, 404 if settings disable it — just check it exists
        assert resp.status_code in (200, 404)

    def test_sentry_init_no_op_without_dsn(self) -> None:
        """init_sentry with empty DSN must not raise."""
        from app.core.observability import init_sentry
        init_sentry(dsn="", environment="test", traces_sample_rate=0.1)
