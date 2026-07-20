"""Unit tests for health endpoints (using fake cache — no Docker required)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_liveness_returns_200(client: TestClient) -> None:
    """GET /api/v1/health returns 200 with status ok."""
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_readiness_ok_with_fake_cache(client: TestClient) -> None:
    """GET /api/v1/health/ready returns 200 when cache is available."""
    resp = client.get("/api/v1/health/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["checks"]["redis"] == "ok"


def test_readiness_503_when_cache_down(
    app_with_fake_cache: object,
    fake_cache_down: object,
) -> None:
    """GET /api/v1/health/ready returns 503 when cache is unavailable."""
    from fastapi import FastAPI

    from app.core.container import get_cache_gateway

    app = app_with_fake_cache  # type: ignore[assignment]
    assert isinstance(app, FastAPI)
    app.dependency_overrides[get_cache_gateway] = lambda: fake_cache_down
    c = TestClient(app, raise_server_exceptions=False)

    resp = c.get("/api/v1/health/ready")
    assert resp.status_code == 503


def test_version_returns_non_empty(client: TestClient) -> None:
    """GET /api/v1/version returns a non-empty version string."""
    resp = client.get("/api/v1/version")
    assert resp.status_code == 200
    body = resp.json()
    assert body["version"]
    assert body["environment"] == "test"
