from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import Workspace
from app.domain.exceptions import NotFoundError
from app.infrastructure.db.models.workspace import WorkspaceModel


def _to_domain(row: WorkspaceModel) -> Workspace:
    return Workspace(
        id=row.id,
        name=row.name,
        plan=row.plan,
        created_at=row.created_at,
    )


def _to_model(entity: Workspace) -> WorkspaceModel:
    return WorkspaceModel(
        id=entity.id,
        name=entity.name,
        plan=entity.plan,
        created_at=entity.created_at,
    )


class SqlAlchemyWorkspaceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, workspace_id: str) -> Workspace:
        result = await self._session.get(WorkspaceModel, workspace_id)
        if result is None:
            raise NotFoundError(f"Workspace {workspace_id!r} not found")
        return _to_domain(result)

    async def save(self, workspace: Workspace) -> Workspace:
        existing = await self._session.get(WorkspaceModel, workspace.id)
        if existing is None:
            row = _to_model(workspace)
            self._session.add(row)
        else:
            existing.name = workspace.name
            existing.plan = workspace.plan
            row = existing
        await self._session.flush()
        await self._session.refresh(row)
        return _to_domain(row)
