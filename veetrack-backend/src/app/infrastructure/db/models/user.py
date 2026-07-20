from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base

if TYPE_CHECKING:
    from app.infrastructure.db.models.audit_log import AuditLogModel
    from app.infrastructure.db.models.watchlist import WatchlistModel
    from app.infrastructure.db.models.workspace import WorkspaceModel


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="viewer")
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    workspace: Mapped[WorkspaceModel] = relationship(
        "WorkspaceModel", back_populates="users", lazy="raise"
    )
    watchlists: Mapped[list[WatchlistModel]] = relationship(
        "WatchlistModel", back_populates="user", lazy="raise"
    )
    audit_logs: Mapped[list[AuditLogModel]] = relationship(
        "AuditLogModel", back_populates="user", lazy="raise"
    )
