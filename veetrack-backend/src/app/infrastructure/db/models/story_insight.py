from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base

if TYPE_CHECKING:
    from app.infrastructure.db.models.story import StoryModel


class StoryInsightModel(Base):
    __tablename__ = "story_insights"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    story_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("stories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    what_happened: Mapped[str] = mapped_column(Text, nullable=False, default="")
    why_happened: Mapped[str] = mapped_column(Text, nullable=False, default="")
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    model_used: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    token_cost: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reasoning_trace: Mapped[list[dict[str, Any]] | None] = mapped_column(
        type_=postgresql.JSONB, nullable=True
    )

    story: Mapped[StoryModel] = relationship("StoryModel", back_populates="insights", lazy="raise")
