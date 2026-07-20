from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base

if TYPE_CHECKING:
    from app.infrastructure.db.models.story import StoryModel
    from app.infrastructure.db.models.watchlist import WatchlistModel


class AlertModel(Base):
    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    watchlist_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("watchlists.id", ondelete="CASCADE"), nullable=False, index=True
    )
    story_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("stories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    channel: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")

    watchlist: Mapped[WatchlistModel] = relationship(
        "WatchlistModel", back_populates="alerts", lazy="raise"
    )
    story: Mapped[StoryModel] = relationship("StoryModel", back_populates="alerts", lazy="raise")
