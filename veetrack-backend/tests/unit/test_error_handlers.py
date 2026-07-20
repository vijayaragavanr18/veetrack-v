"""Unit tests for domain-exception → HTTP mapping."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.error_handlers import register_error_handlers
from app.domain.exceptions import ConflictError, NotFoundError, ValidationError


def _app_with_route(exc: Exception) -> FastAPI:
    """Build a minimal app that raises exc on GET /test."""
    mini_app = FastAPI()
    register_error_handlers(mini_app)

    @mini_app.get("/test")
    async def route() -> dict[str, str]:
        raise exc

    return mini_app


def test_not_found_maps_to_404() -> None:
    """NotFoundError produces a 404 with the correct error body shape."""
    app = _app_with_route(NotFoundError("story abc not found"))
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/test")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"] == "NOT_FOUND"
    assert "abc" in body["message"]


def test_conflict_maps_to_409() -> None:
    """ConflictError produces a 409."""
    app = _app_with_route(ConflictError("duplicate dedup_hash"))
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/test")
    assert resp.status_code == 409
    assert resp.json()["error"] == "CONFLICT"


def test_validation_error_maps_to_422() -> None:
    """Domain ValidationError (not Pydantic's) produces a 422."""
    app = _app_with_route(ValidationError("invalid risk level"))
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/test")
    assert resp.status_code == 422
    assert resp.json()["error"] == "VALIDATION_ERROR"


def test_unhandled_exception_returns_safe_500() -> None:
    """Unexpected exceptions return 500 with a generic message — no traceback."""
    app = _app_with_route(RuntimeError("something internal"))
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/test")
    assert resp.status_code == 500
    body = resp.json()
    assert body["error"] == "INTERNAL_ERROR"
    assert "traceback" not in str(body).lower()
    assert "RuntimeError" not in body["message"]
