from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base

if TYPE_CHECKING:
    from app.infrastructure.db.models.alert import AlertModel
    from app.infrastructure.db.models.entity import EntityModel
    from app.infrastructure.db.models.story_article import StoryArticleModel
    from app.infrastructure.db.models.story_insight import StoryInsightModel
    from app.infrastructure.db.models.story_recommendation import StoryRecommendationModel

EMBEDDING_DIM = 1024


class StoryModel(Base):
    __tablename__ = "stories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    primary_entity_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("entities.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", index=True)
    cluster_centroid: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIM), nullable=True
    )
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False, default="low")
    is_pattern: Mapped[bool] = mapped_column(nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    primary_entity: Mapped[EntityModel] = relationship(
        "EntityModel", back_populates="stories", lazy="raise"
    )
    story_articles: Mapped[list[StoryArticleModel]] = relationship(
        "StoryArticleModel", back_populates="story", lazy="raise", cascade="all, delete-orphan"
    )
    insights: Mapped[list[StoryInsightModel]] = relationship(
        "StoryInsightModel", back_populates="story", lazy="raise", cascade="all, delete-orphan"
    )
    recommendations: Mapped[list[StoryRecommendationModel]] = relationship(
        "StoryRecommendationModel",
        back_populates="story",
        lazy="raise",
        cascade="all, delete-orphan",
    )
    alerts: Mapped[list[AlertModel]] = relationship(
        "AlertModel", back_populates="story", lazy="raise"
    )

    __table_args__ = (
        Index(
            "ix_stories_cluster_centroid_hnsw",
            "cluster_centroid",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"cluster_centroid": "vector_cosine_ops"},
        ),
    )
