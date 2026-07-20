from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import User
from app.domain.exceptions import NotFoundError
from app.infrastructure.db.models.user import UserModel


def _to_domain(row: UserModel) -> User:
    return User(
        id=row.id,
        workspace_id=row.workspace_id,
        email=row.email,
        role=row.role,  # type: ignore[arg-type]
        hashed_password=row.hashed_password,
        created_at=row.created_at,
    )


def _to_model(entity: User) -> UserModel:
    return UserModel(
        id=entity.id,
        workspace_id=entity.workspace_id,
        email=entity.email,
        role=entity.role,
        hashed_password=entity.hashed_password,
        created_at=entity.created_at,
    )


class SqlAlchemyUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: str) -> User:
        result = await self._session.get(UserModel, user_id)
        if result is None:
            raise NotFoundError(f"User {user_id!r} not found")
        return _to_domain(result)

    async def get_by_email(self, email: str, workspace_id: str) -> User | None:
        stmt = select(UserModel).where(
            UserModel.email == email,
            UserModel.workspace_id == workspace_id,
        )
        result = await self._session.scalar(stmt)
        return _to_domain(result) if result is not None else None

    async def save(self, user: User) -> User:
        existing = await self._session.get(UserModel, user.id)
        if existing is None:
            row = _to_model(user)
            self._session.add(row)
        else:
            existing.email = user.email
            existing.role = user.role
            existing.hashed_password = user.hashed_password
            row = existing
        await self._session.flush()
        await self._session.refresh(row)
        return _to_domain(row)
