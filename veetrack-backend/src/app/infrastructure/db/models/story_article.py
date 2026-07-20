from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base

if TYPE_CHECKING:
    from app.infrastructure.db.models.article import ArticleModel
    from app.infrastructure.db.models.story import StoryModel


class StoryArticleModel(Base):
    __tablename__ = "story_articles"

    story_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("stories.id", ondelete="CASCADE"), primary_key=True
    )
    article_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    story: Mapped[StoryModel] = relationship(
        "StoryModel", back_populates="story_articles", lazy="raise"
    )
    article: Mapped[ArticleModel] = relationship(
        "ArticleModel", back_populates="story_articles", lazy="raise"
    )
