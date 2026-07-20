"""Integration tests: RBAC enforcement at the dependency layer.

Uses a minimal test endpoint registered only during tests (not shipped to production).
Requires Postgres.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import Annotated

import asyncpg
import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from app.core.security_deps import require_role
from app.domain.entities import User
from app.domain.value_objects.role import Role

DATABASE_URL = os.getenv("DATABASE_URL", "")


def _db_reachable() -> bool:
    async def _check() -> bool:
        try:
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


def _set_user_role(user_id: str, role: str) -> None:
    """Directly update a user's role in the DB — test fixture helper only."""

    async def _run() -> None:
        conn = await asyncpg.connect(DATABASE_URL.replace("+asyncpg", ""))
        try:
            await conn.execute("UPDATE users SET role = $1 WHERE id = $2", role, user_id)
        finally:
            await conn.close()

    asyncio.run(_run())


def _make_rbac_client() -> tuple[TestClient, dict[str, str]]:
    """Return a client and tokens for owner/analyst/viewer roles.

    Register users (all become 'owner'), then patch analyst/viewer roles in the DB
    and re-issue tokens with the correct role so RBAC enforcement is actually tested.
    """
    from jose import jwt as jose_jwt  # type: ignore[import-untyped]

    from app.core.config import get_settings
    from app.core.container import _build_cache_gateway
    from app.infrastructure.security.jwt_service import JwtService
    from app.main import create_app

    _build_cache_gateway.cache_clear()  # type: ignore[attr-defined]
    app = create_app()

    @app.get("/test/admin-only")
    async def admin_only(
        user: Annotated[User, Depends(require_role(Role.admin))],
    ) -> dict[str, str]:
        return {"ok": user.role}

    @app.get("/test/analyst-only")
    async def analyst_only(
        user: Annotated[User, Depends(require_role(Role.analyst))],
    ) -> dict[str, str]:
        return {"ok": user.role}

    client = TestClient(app, raise_server_exceptions=False)
    suffix = uuid.uuid4().hex[:8]
    settings = get_settings()
    jwt_svc = JwtService(settings.jwt_secret)

    def _register(email: str, workspace: str) -> str:
        reg = client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "Pass1234!", "workspace_name": workspace},
        )
        assert reg.status_code == 201, f"Register failed ({reg.status_code}): {reg.text}"
        return reg.json()["access_token"]

    def _token_with_role(access_token: str, role: str) -> str:
        """Decode the access token to get sub/wid, patch DB role, re-issue token."""
        payload = jose_jwt.decode(
            access_token,
            settings.jwt_secret,
            algorithms=["HS256"],
        )
        user_id: str = payload["sub"]
        workspace_id: str = payload["wid"]
        _set_user_role(user_id, role)
        return jwt_svc.create_access_token(user_id, workspace_id, role)

    owner_token = _register(f"owner_{suffix}@example.com", f"Owner Corp {suffix}")
    analyst_token = _token_with_role(
        _register(f"analyst_{suffix}@example.com", f"Analyst Corp {suffix}"),
        "analyst",
    )
    viewer_token = _token_with_role(
        _register(f"viewer_{suffix}@example.com", f"Viewer Corp {suffix}"),
        "viewer",
    )

    return client, {"owner": owner_token, "analyst": analyst_token, "viewer": viewer_token}


@requires_db
def test_owner_can_access_admin_endpoint() -> None:
    client, tokens = _make_rbac_client()
    resp = client.get("/test/admin-only", headers={"Authorization": f"Bearer {tokens['owner']}"})
    assert resp.status_code == 200


@requires_db
def test_analyst_cannot_access_admin_endpoint() -> None:
    client, tokens = _make_rbac_client()
    resp = client.get("/test/admin-only", headers={"Authorization": f"Bearer {tokens['analyst']}"})
    assert resp.status_code == 403


@requires_db
def test_viewer_cannot_access_admin_endpoint() -> None:
    client, tokens = _make_rbac_client()
    resp = client.get("/test/admin-only", headers={"Authorization": f"Bearer {tokens['viewer']}"})
    assert resp.status_code == 403


@requires_db
def test_analyst_can_access_analyst_endpoint() -> None:
    client, tokens = _make_rbac_client()
    resp = client.get(
        "/test/analyst-only", headers={"Authorization": f"Bearer {tokens['analyst']}"}
    )
    assert resp.status_code == 200


@requires_db
def test_viewer_cannot_access_analyst_endpoint() -> None:
    client, tokens = _make_rbac_client()
    resp = client.get("/test/analyst-only", headers={"Authorization": f"Bearer {tokens['viewer']}"})
    assert resp.status_code == 403


@requires_db
def test_unauthenticated_returns_401() -> None:
    client, _ = _make_rbac_client()
    resp = client.get("/test/admin-only")
    assert resp.status_code == 401
