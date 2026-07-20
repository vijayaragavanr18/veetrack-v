from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base

if TYPE_CHECKING:
    from app.infrastructure.db.models.audit_log import AuditLogModel
    from app.infrastructure.db.models.user import UserModel
    from app.infrastructure.db.models.watchlist import WatchlistModel


class WorkspaceModel(Base):
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    plan: Mapped[str] = mapped_column(String(50), nullable=False, default="free")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    users: Mapped[list[UserModel]] = relationship(
        "UserModel", back_populates="workspace", lazy="raise"
    )
    watchlists: Mapped[list[WatchlistModel]] = relationship(
        "WatchlistModel", back_populates="workspace", lazy="raise"
    )
    audit_logs: Mapped[list[AuditLogModel]] = relationship(
        "AuditLogModel", back_populates="workspace", lazy="raise"
    )
