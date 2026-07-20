from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base

if TYPE_CHECKING:
    from app.infrastructure.db.models.article_entity import ArticleEntityModel
    from app.infrastructure.db.models.entity_alias import EntityAliasModel
    from app.infrastructure.db.models.story import StoryModel
    from app.infrastructure.db.models.watchlist import WatchlistModel


class EntityModel(Base):
    __tablename__ = "entities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    canonical_name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False, default="topic")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    aliases: Mapped[list[EntityAliasModel]] = relationship("EntityAliasModel", back_populates="entity", lazy="raise", cascade="all, delete-orphan")
    article_entities: Mapped[list[ArticleEntityModel]] = relationship("ArticleEntityModel", back_populates="entity", lazy="raise")
    stories: Mapped[list[StoryModel]] = relationship("StoryModel", back_populates="primary_entity", lazy="raise")
    watchlists: Mapped[list[WatchlistModel]] = relationship("WatchlistModel", back_populates="entity", lazy="raise")
