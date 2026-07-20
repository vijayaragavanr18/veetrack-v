"""Initial schema — all tables, pgvector extension, indexes.

Revision ID: 0001
Revises: (none)
Create Date: 2026-07-15
"""

from __future__ import annotations

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

EMBEDDING_DIM = 1024


def upgrade() -> None:
    # Extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # workspaces
    op.create_table(
        "workspaces",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("plan", sa.String(50), nullable=False, server_default="free"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )

    # users
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="viewer"),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_users_workspace_id", "users", ["workspace_id"])

    # sources
    op.create_table(
        "sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("config_json", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("rate_limit_budget", sa.Float, nullable=False, server_default="1.0"),
    )

    # entities
    op.create_table(
        "entities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("canonical_name", sa.String(255), nullable=False),
        sa.Column("type", sa.String(20), nullable=False, server_default="topic"),
        sa.Column("metadata_json", sa.JSON, nullable=False, server_default="{}"),
    )

    # entity_aliases
    op.create_table(
        "entity_aliases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "entity_id",
            sa.String(36),
            sa.ForeignKey("entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("alias_text", sa.String(255), nullable=False),
        sa.Column("alias_type", sa.String(20), nullable=False, server_default="name"),
    )
    op.create_index("ix_entity_aliases_entity_id", "entity_aliases", ["entity_id"])
    op.create_index("ix_entity_aliases_alias_text", "entity_aliases", ["alias_text"])

    # articles
    op.create_table(
        "articles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "source_id",
            sa.String(36),
            sa.ForeignKey("sources.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("headline", sa.String(1024), nullable=False),
        sa.Column("hero_image_url", sa.String(2048), nullable=True),
        sa.Column("publisher", sa.String(255), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_content", sa.Text, nullable=False, server_default=""),
        sa.Column("clean_content", sa.Text, nullable=False, server_default=""),
        sa.Column("language", sa.String(10), nullable=False, server_default="en"),
        sa.Column("sentiment_label", sa.String(20), nullable=False, server_default="neutral"),
        sa.Column("sentiment_score", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True),
        sa.Column("dedup_hash", sa.String(64), nullable=False),
        sa.Column(
            "ingested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_articles_source_id", "articles", ["source_id"])
    op.create_index("ix_articles_published_at", "articles", ["published_at"])
    op.create_index("ix_articles_dedup_hash", "articles", ["dedup_hash"], unique=True)
    # HNSW index for cosine similarity on embeddings
    op.execute(
        "CREATE INDEX ix_articles_embedding_hnsw ON articles "
        "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )
    # GIN trigram indexes for full-text cold-path search
    op.execute(
        "CREATE INDEX ix_articles_headline_gin ON articles USING gin (headline gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX ix_articles_clean_content_gin ON articles "
        "USING gin (clean_content gin_trgm_ops)"
    )

    # article_entities
    op.create_table(
        "article_entities",
        sa.Column(
            "article_id",
            sa.String(36),
            sa.ForeignKey("articles.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "entity_id",
            sa.String(36),
            sa.ForeignKey("entities.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("relevance_score", sa.Float, nullable=False, server_default="0.0"),
    )

    # stories
    op.create_table(
        "stories",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "primary_entity_id",
            sa.String(36),
            sa.ForeignKey("entities.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("title", sa.String(1024), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("cluster_centroid", Vector(EMBEDDING_DIM), nullable=True),
        sa.Column("risk_level", sa.String(20), nullable=False, server_default="low"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_stories_primary_entity_id", "stories", ["primary_entity_id"])
    op.create_index("ix_stories_status", "stories", ["status"])
    op.create_index("ix_stories_created_at", "stories", ["created_at"])
    op.execute(
        "CREATE INDEX ix_stories_cluster_centroid_hnsw ON stories "
        "USING hnsw (cluster_centroid vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )

    # story_articles
    op.create_table(
        "story_articles",
        sa.Column(
            "story_id",
            sa.String(36),
            sa.ForeignKey("stories.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "article_id",
            sa.String(36),
            sa.ForeignKey("articles.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "added_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )

    # story_insights
    op.create_table(
        "story_insights",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "story_id",
            sa.String(36),
            sa.ForeignKey("stories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("what_happened", sa.Text, nullable=False, server_default=""),
        sa.Column("why_happened", sa.Text, nullable=False, server_default=""),
        sa.Column(
            "generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("model_used", sa.String(100), nullable=False, server_default=""),
        sa.Column("token_cost", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index("ix_story_insights_story_id", "story_insights", ["story_id"])

    # story_recommendations
    op.create_table(
        "story_recommendations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "story_id",
            sa.String(36),
            sa.ForeignKey("stories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("recommendation_text", sa.Text, nullable=False, server_default=""),
        sa.Column("audience", sa.String(20), nullable=False, server_default="exec"),
        sa.Column("risk_level", sa.String(20), nullable=False, server_default="low"),
        sa.Column("confidence_score", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("needs_human_review", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_story_recs_story_id", "story_recommendations", ["story_id"])
    op.create_index(
        "ix_story_recs_story_confidence", "story_recommendations", ["story_id", "confidence_score"]
    )

    # watchlists
    op.create_table(
        "watchlists",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "entity_id",
            sa.String(36),
            sa.ForeignKey("entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("alert_channels_json", sa.JSON, nullable=False, server_default="{}"),
    )
    op.create_index("ix_watchlists_workspace_id", "watchlists", ["workspace_id"])
    op.create_index("ix_watchlists_user_id", "watchlists", ["user_id"])
    op.create_index("ix_watchlists_entity_id", "watchlists", ["entity_id"])

    # alerts
    op.create_table(
        "alerts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "watchlist_id",
            sa.String(36),
            sa.ForeignKey("watchlists.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "story_id",
            sa.String(36),
            sa.ForeignKey("stories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "sent_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("channel", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
    )
    op.create_index("ix_alerts_watchlist_id", "alerts", ["watchlist_id"])
    op.create_index("ix_alerts_story_id", "alerts", ["story_id"])

    # audit_log
    op.create_table(
        "audit_log",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(100), nullable=False),
        sa.Column("resource_id", sa.String(36), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_audit_log_workspace_id", "audit_log", ["workspace_id"])
    op.create_index("ix_audit_log_user_id", "audit_log", ["user_id"])
    op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"])

    # api_usage_log
    op.create_table(
        "api_usage_log",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "source_id",
            sa.String(36),
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("calls_made", sa.Integer, nullable=False, server_default="0"),
        sa.Column("quota_limit", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "window_start", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_api_usage_log_source_id", "api_usage_log", ["source_id"])


def downgrade() -> None:
    op.drop_table("api_usage_log")
    op.drop_table("audit_log")
    op.drop_table("alerts")
    op.drop_table("watchlists")
    op.drop_table("story_recommendations")
    op.drop_table("story_insights")
    op.drop_table("story_articles")
    op.drop_table("stories")
    op.drop_table("article_entities")
    op.drop_table("articles")
    op.drop_table("entity_aliases")
    op.drop_table("entities")
    op.drop_table("sources")
    op.drop_table("users")
    op.drop_table("workspaces")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
    op.execute("DROP EXTENSION IF EXISTS vector")
