from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base

if TYPE_CHECKING:
    from app.infrastructure.db.models.story import StoryModel


class StoryRecommendationModel(Base):
    __tablename__ = "story_recommendations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    story_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("stories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recommendation_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    audience: Mapped[str] = mapped_column(String(20), nullable=False, default="exec")
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False, default="low")
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    needs_human_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    story: Mapped[StoryModel] = relationship(
        "StoryModel", back_populates="recommendations", lazy="raise"
    )

    __table_args__ = (Index("ix_story_recs_story_confidence", "story_id", "confidence_score"),)
