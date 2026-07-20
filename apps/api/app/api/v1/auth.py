"""Authentication endpoints.

POST /auth/register  — create workspace + owner account
POST /auth/login     — returns access token (JSON) + sets refresh httpOnly cookie
POST /auth/refresh   — exchanges refresh cookie for new access token
POST /auth/logout    — clears the refresh cookie
GET  /auth/me        — returns the current authenticated user
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Cookie, Depends, Response

from app.application.dto.auth import LoginRequest, RegisterRequest, TokenPair, UserResponse
from app.application.use_cases.auth.login import Login
from app.application.use_cases.auth.refresh_token import RefreshToken
from app.application.use_cases.auth.register_user import RegisterUser
from app.core.container import (
    get_jwt_service,
    get_login_use_case,
    get_refresh_use_case,
    get_register_use_case,
)
from app.core.security_deps import get_current_user
from app.domain.entities import User
from app.domain.exceptions import UnauthorizedError
from app.infrastructure.security.jwt_service import REFRESH_TOKEN_DAYS, JwtService

router = APIRouter(prefix="/auth", tags=["auth"])
logger = structlog.get_logger(__name__)

_REFRESH_COOKIE = "vt_refresh"
_COOKIE_MAX_AGE = REFRESH_TOKEN_DAYS * 86_400


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=_REFRESH_COOKIE,
        value=refresh_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=_COOKIE_MAX_AGE,
        path="/api/v1/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key=_REFRESH_COOKIE, path="/api/v1/auth")


@router.post("/register", response_model=TokenPair, status_code=201)
async def register(
    req: RegisterRequest,
    use_case: Annotated[RegisterUser, Depends(get_register_use_case)],
    jwt_service: Annotated[JwtService, Depends(get_jwt_service)],
    response: Response,
) -> TokenPair:
    user, workspace, tokens = await use_case.execute(req)
    refresh = jwt_service.create_refresh_token(user.id)
    _set_refresh_cookie(response, refresh)
    logger.info("auth.register", user_id=user.id, workspace_id=workspace.id)
    return tokens


@router.post("/login", response_model=TokenPair)
async def login(
    req: LoginRequest,
    use_case: Annotated[Login, Depends(get_login_use_case)],
    jwt_service: Annotated[JwtService, Depends(get_jwt_service)],
    response: Response,
) -> TokenPair:
    user, tokens = await use_case.execute(req)
    refresh = jwt_service.create_refresh_token(user.id)
    _set_refresh_cookie(response, refresh)
    logger.info("auth.login", user_id=user.id)
    return tokens


@router.post("/refresh", response_model=TokenPair)
async def refresh(
    use_case: Annotated[RefreshToken, Depends(get_refresh_use_case)],
    jwt_service: Annotated[JwtService, Depends(get_jwt_service)],
    response: Response,
    vt_refresh: Annotated[str | None, Cookie()] = None,
) -> TokenPair:
    if vt_refresh is None:
        raise UnauthorizedError("Missing refresh token")
    tokens = await use_case.execute(vt_refresh)
    # Rotate refresh token

    user_id = jwt_service.decode_refresh_token(vt_refresh)
    new_refresh = jwt_service.create_refresh_token(user_id)
    _set_refresh_cookie(response, new_refresh)
    logger.info("auth.refresh", user_id=user_id)
    return tokens


@router.post("/logout", status_code=204)
async def logout(response: Response) -> None:
    _clear_refresh_cookie(response)


@router.get("/me", response_model=UserResponse)
async def me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserResponse:
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        role=current_user.role,
        workspace_id=current_user.workspace_id,
    )
