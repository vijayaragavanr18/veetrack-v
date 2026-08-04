"""Add reasoning_trace column to story_recommendations.

Stores the full ReAct loop trace (tool calls, observations, model reasoning)
for every agentic recommendation run. Null for single-shot fallback rows.

Revision ID: 0005
Revises: 0004
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "story_recommendations",
        sa.Column("reasoning_trace", sa.JSON, nullable=True),
    )
    op.add_column(
        "story_recommendations",
        sa.Column("agent_mode", sa.String(20), nullable=False, server_default="single_shot"),
    )


def downgrade() -> None:
    op.drop_column("story_recommendations", "agent_mode")
    op.drop_column("story_recommendations", "reasoning_trace")
