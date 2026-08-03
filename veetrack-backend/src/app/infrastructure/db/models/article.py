from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base

if TYPE_CHECKING:
    from app.infrastructure.db.models.article_entity import ArticleEntityModel
    from app.infrastructure.db.models.source import SourceModel
    from app.infrastructure.db.models.story_article import StoryArticleModel

EMBEDDING_DIM = 1024


class ArticleModel(Base):
    __tablename__ = "articles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    headline: Mapped[str] = mapped_column(String(1024), nullable=False)
    hero_image_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    publisher: Mapped[str] = mapped_column(String(255), nullable=False)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    raw_content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    clean_content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    sentiment_label: Mapped[str] = mapped_column(String(20), nullable=False, default="neutral")
    sentiment_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    dedup_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    dedup_verdict: Mapped[str | None] = mapped_column(String(20), nullable=True)
    dedup_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    dedup_agent_path: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'fast_path'")
    )
    is_duplicate_of: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("articles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    source: Mapped[SourceModel] = relationship(
        "SourceModel", back_populates="articles", lazy="raise"
    )
    article_entities: Mapped[list[ArticleEntityModel]] = relationship(
        "ArticleEntityModel", back_populates="article", lazy="raise", cascade="all, delete-orphan"
    )
    story_articles: Mapped[list[StoryArticleModel]] = relationship(
        "StoryArticleModel", back_populates="article", lazy="raise"
    )

    __table_args__ = (
        # HNSW index for cosine similarity search on embeddings
        Index(
            "ix_articles_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        # GIN trigram indexes for cold-path full-text search
        Index(
            "ix_articles_headline_gin",
            "headline",
            postgresql_using="gin",
            postgresql_ops={"headline": "gin_trgm_ops"},
        ),
        Index(
            "ix_articles_clean_content_gin",
            "clean_content",
            postgresql_using="gin",
            postgresql_ops={"clean_content": "gin_trgm_ops"},
        ),
    )
