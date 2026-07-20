"""Use case: resolve a validated access token payload to a full User entity."""

from __future__ import annotations

from typing import Any

from app.domain.entities import User
from app.domain.interfaces.repositories import UserRepository


class GetCurrentUser:
    def __init__(self, user_repo: UserRepository) -> None:
        self._users = user_repo

    async def execute(self, token_payload: dict[str, Any]) -> User:
        user_id: str = token_payload["sub"]
        return await self._users.get_by_id(user_id)
