from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base

if TYPE_CHECKING:
    from app.infrastructure.db.models.alert import AlertModel
    from app.infrastructure.db.models.entity import EntityModel
    from app.infrastructure.db.models.user import UserModel
    from app.infrastructure.db.models.workspace import WorkspaceModel


class WatchlistModel(Base):
    __tablename__ = "watchlists"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entity_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    alert_channels_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    workspace: Mapped[WorkspaceModel] = relationship(
        "WorkspaceModel", back_populates="watchlists", lazy="raise"
    )
    user: Mapped[UserModel] = relationship("UserModel", back_populates="watchlists", lazy="raise")
    entity: Mapped[EntityModel] = relationship(
        "EntityModel", back_populates="watchlists", lazy="raise"
    )
    alerts: Mapped[list[AlertModel]] = relationship(
        "AlertModel", back_populates="watchlist", lazy="raise", cascade="all, delete-orphan"
    )
