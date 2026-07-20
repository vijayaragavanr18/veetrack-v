"""Use case: exchange a valid refresh token for a new token pair (rotation)."""

from __future__ import annotations

from app.application.dto.auth import TokenPair
from app.domain.interfaces.repositories import UserRepository
from app.domain.interfaces.security import TokenService


class RefreshToken:
    def __init__(self, user_repo: UserRepository, token_service: TokenService) -> None:
        self._users = user_repo
        self._tokens = token_service

    async def execute(self, refresh_token: str) -> TokenPair:
        user_id = self._tokens.decode_refresh_token(refresh_token)
        user = await self._users.get_by_id(user_id)

        return TokenPair(
            access_token=self._tokens.create_access_token(user.id, user.workspace_id, user.role),
        )
