"""Add is_duplicate_of column to articles for near-duplicate flagging.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-16
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "articles",
        sa.Column(
            "is_duplicate_of",
            sa.String(36),
            sa.ForeignKey("articles.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_articles_is_duplicate_of", "articles", ["is_duplicate_of"])


def downgrade() -> None:
    op.drop_index("ix_articles_is_duplicate_of", table_name="articles")
    op.drop_column("articles", "is_duplicate_of")
