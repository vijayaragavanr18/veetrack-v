"""Add user_feedback, agent_path, reasoning_trace to alerts table.

user_feedback: 'useful' | 'not_useful' | null — populated by the frontend feedback UI.
agent_path: 'fast_path' | 'agentic' | 'fallback' — which decision path fired.
reasoning_trace: JSON array of ReAct loop trace entries; null for fast_path rows.

Revision ID: 0006
Revises: 0005
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "alerts",
        sa.Column("user_feedback", sa.String(20), nullable=True),
    )
    op.add_column(
        "alerts",
        sa.Column(
            "agent_path",
            sa.String(20),
            nullable=False,
            server_default="fast_path",
        ),
    )
    op.add_column(
        "alerts",
        sa.Column("reasoning_trace", sa.JSON, nullable=True),
    )
    # Index for feedback queries (get_alert_feedback_history tool)
    op.create_index(
        "ix_alerts_watchlist_feedback",
        "alerts",
        ["watchlist_id", "user_feedback"],
        postgresql_where=sa.text("user_feedback IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_alerts_watchlist_feedback", table_name="alerts")
    op.drop_column("alerts", "reasoning_trace")
    op.drop_column("alerts", "agent_path")
    op.drop_column("alerts", "user_feedback")
