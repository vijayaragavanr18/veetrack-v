"""Use case: register a new workspace + owner user."""

from __future__ import annotations

from app.application.dto.auth import RegisterRequest, TokenPair
from app.domain.entities import User, Workspace
from app.domain.exceptions import ConflictError
from app.domain.interfaces.repositories import UserRepository, WorkspaceRepository
from app.domain.interfaces.security import PasswordHasher, TokenService


class RegisterUser:
    def __init__(
        self,
        user_repo: UserRepository,
        workspace_repo: WorkspaceRepository,
        password_hasher: PasswordHasher,
        token_service: TokenService,
    ) -> None:
        self._users = user_repo
        self._workspaces = workspace_repo
        self._hasher = password_hasher
        self._tokens = token_service

    async def execute(self, req: RegisterRequest) -> tuple[User, Workspace, TokenPair]:
        workspace = Workspace(name=req.workspace_name)
        workspace = await self._workspaces.save(workspace)

        existing = await self._users.get_by_email(req.email, workspace.id)
        if existing is not None:
            raise ConflictError(f"Email {req.email!r} already registered in this workspace")

        user = User(
            workspace_id=workspace.id,
            email=req.email,
            role="owner",
            hashed_password=self._hasher.hash(req.password),
        )
        user = await self._users.save(user)

        tokens = TokenPair(
            access_token=self._tokens.create_access_token(user.id, workspace.id, user.role),
        )
        return user, workspace, tokens
