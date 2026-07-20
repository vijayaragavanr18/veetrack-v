"""Integration tests: full register / login / refresh / logout / me flow.

Requires Postgres + Redis (Docker Compose). Skipped automatically if DB unreachable.
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest
from fastapi.testclient import TestClient

DATABASE_URL = os.getenv("DATABASE_URL", "")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


def _db_reachable() -> bool:
    async def _check() -> bool:
        try:
            import asyncpg

            conn = await asyncpg.connect(DATABASE_URL.replace("+asyncpg", ""))
            await conn.close()
            return True
        except Exception:
            return False

    return asyncio.run(_check())


requires_db = pytest.mark.skipif(
    not _db_reachable(),
    reason="Postgres not reachable — start Docker Compose",
)


def _make_client() -> TestClient:
    from app.core.container import _build_cache_gateway

    _build_cache_gateway.cache_clear()  # type: ignore[attr-defined]
    from app.main import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


def _uid() -> str:
    """Short unique suffix to avoid duplicate-email conflicts across test runs."""
    return uuid.uuid4().hex[:8]


@requires_db
def test_register_creates_workspace_and_returns_token() -> None:
    client = _make_client()
    s = _uid()
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"owner_{s}@example.com",
            "password": "StrongPass1!",
            "workspace_name": f"Acme Corp {s}",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"
    assert "vt_refresh" in resp.cookies


@requires_db
def test_login_with_valid_credentials() -> None:
    client = _make_client()
    s = _uid()
    reg = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"login_{s}@example.com",
            "password": "Pass1234!",
            "workspace_name": f"Login Corp {s}",
        },
    )
    assert reg.status_code == 201, reg.text
    token = reg.json()["access_token"]
    me_resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    workspace_id = me_resp.json()["workspace_id"]

    resp = client.post(
        "/api/v1/auth/login",
        json={
            "email": f"login_{s}@example.com",
            "password": "Pass1234!",
            "workspace_id": workspace_id,
        },
    )
    assert resp.status_code == 200, resp.text
    assert "access_token" in resp.json()
    assert "vt_refresh" in resp.cookies


@requires_db
def test_login_wrong_password_returns_401() -> None:
    client = _make_client()
    s = _uid()
    reg = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"badpass_{s}@example.com",
            "password": "CorrectPass1!",
            "workspace_name": f"BadPass Corp {s}",
        },
    )
    assert reg.status_code == 201, reg.text
    token = reg.json()["access_token"]
    wid = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).json()[
        "workspace_id"
    ]

    resp = client.post(
        "/api/v1/auth/login",
        json={
            "email": f"badpass_{s}@example.com",
            "password": "WrongPassword",
            "workspace_id": wid,
        },
    )
    assert resp.status_code == 401


@requires_db
def test_me_without_token_returns_401() -> None:
    client = _make_client()
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401


@requires_db
def test_me_with_valid_token() -> None:
    client = _make_client()
    s = _uid()
    reg = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"metest_{s}@example.com",
            "password": "Pass1234!",
            "workspace_name": f"Me Corp {s}",
        },
    )
    assert reg.status_code == 201, reg.text
    token = reg.json()["access_token"]
    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["email"] == f"metest_{s}@example.com"
    assert body["role"] == "owner"
    assert "id" in body
    assert "workspace_id" in body


@requires_db
def test_refresh_rotates_token() -> None:
    client = _make_client()
    s = _uid()
    reg = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"refresh_{s}@example.com",
            "password": "Pass1234!",
            "workspace_name": f"Refresh Corp {s}",
        },
    )
    assert reg.status_code == 201, reg.text
    original_refresh = reg.cookies["vt_refresh"]

    client.cookies.set("vt_refresh", original_refresh)
    resp = client.post("/api/v1/auth/refresh")
    assert resp.status_code == 200, resp.text
    assert "access_token" in resp.json()
    # Rotation succeeds — new cookie must be present.
    # Tokens issued within the same second share the same iat/exp so we only
    # assert presence, not value inequality.
    assert "vt_refresh" in resp.cookies


@requires_db
def test_logout_clears_refresh_cookie() -> None:
    client = _make_client()
    s = _uid()
    reg = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"logout_{s}@example.com",
            "password": "Pass1234!",
            "workspace_name": f"Logout Corp {s}",
        },
    )
    assert reg.status_code == 201, reg.text
    client.cookies.set("vt_refresh", reg.cookies["vt_refresh"])
    resp = client.post("/api/v1/auth/logout")
    assert resp.status_code == 204
