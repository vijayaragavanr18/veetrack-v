"""Add llm_usage_log table for tracking LLM API usage and cost.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-16
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_usage_log",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "story_id",
            sa.String(36),
            sa.ForeignKey("stories.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("model_id", sa.String(100), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "cost_usd_micro",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Approximate cost in millionths of USD (micro-USD)",
        ),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("llm_usage_log")
