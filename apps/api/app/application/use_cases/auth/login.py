"""Use case: authenticate with email + password, return token pair."""

from __future__ import annotations

from app.application.dto.auth import LoginRequest, TokenPair
from app.domain.entities import User
from app.domain.exceptions import UnauthorizedError
from app.domain.interfaces.repositories import UserRepository
from app.domain.interfaces.security import PasswordHasher, TokenService


class Login:
    def __init__(
        self,
        user_repo: UserRepository,
        password_hasher: PasswordHasher,
        token_service: TokenService,
    ) -> None:
        self._users = user_repo
        self._hasher = password_hasher
        self._tokens = token_service

    async def execute(self, req: LoginRequest) -> tuple[User, TokenPair]:
        user = await self._users.get_by_email(req.email, req.workspace_id)
        if user is None or not self._hasher.verify(req.password, user.hashed_password):
            raise UnauthorizedError("Invalid credentials")

        tokens = TokenPair(
            access_token=self._tokens.create_access_token(user.id, user.workspace_id, user.role),
        )
        return user, tokens
