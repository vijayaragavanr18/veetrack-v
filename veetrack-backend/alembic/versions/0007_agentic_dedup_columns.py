"""Add dedup_verdict, dedup_reasoning, dedup_agent_path to articles table.

dedup_verdict:    'duplicate' | 'update' | 'distinct' | null (null = not yet evaluated
                  or resolved on fast path without explicit verdict storage).
dedup_reasoning:  Free-text reasoning from the agentic path; null on fast path.
dedup_agent_path: 'fast_path' | 'agentic' | 'fallback' — which decision path ran.
                  DEFAULT 'fast_path' so existing rows remain valid.

Revision ID: 0007
Revises: 0006
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "articles",
        sa.Column(
            "dedup_verdict",
            sa.String(20),
            nullable=True,
        ),
    )
    op.add_column(
        "articles",
        sa.Column(
            "dedup_reasoning",
            sa.Text(),
            nullable=True,
        ),
    )
    op.add_column(
        "articles",
        sa.Column(
            "dedup_agent_path",
            sa.String(20),
            nullable=False,
            server_default="fast_path",
        ),
    )
    # Partial index for agentic rows — useful for analytics and reprocessing queries.
    op.create_index(
        "ix_articles_agentic_dedup",
        "articles",
        ["dedup_agent_path"],
        postgresql_where=sa.text("dedup_agent_path != 'fast_path'"),
    )


def downgrade() -> None:
    op.drop_index("ix_articles_agentic_dedup", table_name="articles")
    op.drop_column("articles", "dedup_agent_path")
    op.drop_column("articles", "dedup_reasoning")
    op.drop_column("articles", "dedup_verdict")
