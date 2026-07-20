from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base

if TYPE_CHECKING:
    from app.infrastructure.db.models.article import ArticleModel
    from app.infrastructure.db.models.entity import EntityModel


class ArticleEntityModel(Base):
    __tablename__ = "article_entities"

    article_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True
    )
    entity_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True
    )
    relevance_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    article: Mapped[ArticleModel] = relationship("ArticleModel", back_populates="article_entities", lazy="raise")
    entity: Mapped[EntityModel] = relationship("EntityModel", back_populates="article_entities", lazy="raise")
