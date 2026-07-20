"""FastAPI security dependencies: token extraction, identity resolution, role gating.

Every protected endpoint uses Depends(get_current_user) or Depends(require_role(Role.analyst))
— never trust implicit state.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Annotated, Any

import structlog
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.container import get_db_session, get_jwt_service
from app.domain.entities import User
from app.domain.exceptions import ForbiddenError, UnauthorizedError
from app.domain.value_objects.role import Role
from app.infrastructure.security.jwt_service import JwtService

logger = structlog.get_logger(__name__)

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    jwt_service: Annotated[JwtService, Depends(get_jwt_service)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> User:
    """Resolve a Bearer access token to the authenticated User.

    Raises UnauthorizedError (→ 401) if the token is absent or invalid.
    """
    if credentials is None:
        raise UnauthorizedError("Missing Bearer token")

    payload = jwt_service.decode_access_token(credentials.credentials)

    from app.infrastructure.db.repositories.user import SqlAlchemyUserRepository

    user = await SqlAlchemyUserRepository(session).get_by_id(payload["sub"])
    return user


async def get_optional_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    jwt_service: Annotated[JwtService, Depends(get_jwt_service)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> User | None:
    """Like get_current_user but returns None instead of raising when no token."""
    if credentials is None:
        return None
    try:
        payload = jwt_service.decode_access_token(credentials.credentials)
        from app.infrastructure.db.repositories.user import SqlAlchemyUserRepository
        return await SqlAlchemyUserRepository(session).get_by_id(payload["sub"])
    except Exception:
        return None


def require_role(min_role: Role) -> Callable[[User], Coroutine[Any, Any, User]]:
    """Return a dependency that enforces a minimum role level.

    Usage:
        @router.get("/admin/stuff")
        async def admin_stuff(
            user: Annotated[User, Depends(require_role(Role.admin))],
        ) -> ...:
    """

    async def _check(
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        try:
            user_role = Role.from_str(current_user.role)
        except ValueError as exc:
            raise ForbiddenError("Unknown role") from exc
        if user_role < min_role:
            raise ForbiddenError(
                f"Requires {min_role.name} role or higher (you have {current_user.role})"
            )
        return current_user

    return _check
