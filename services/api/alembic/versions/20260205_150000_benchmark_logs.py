"""Phase 7: Benchmark Logs — structured logging for emergent scoring.

Adds:
- benchmark_logs table for capturing every interaction
- Learning fills in assessments async
- User signals inferred from follow-up behavior

Revision ID: benchmark_logs_001
Revises: telegram_users_001
Create Date: 2026-02-05 15:00:00.000000

"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "benchmark_logs_001"
down_revision: str | None = "telegram_users_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create benchmark_logs table."""
    op.create_table(
        "benchmark_logs",
        # Primary key
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # Foreign keys
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("sessions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("turn_number", sa.Integer(), nullable=False),
        sa.Column("is_heartbeat", sa.Boolean(), server_default="false"),
        # Input
        sa.Column("user_query", sa.Text(), nullable=False),
        sa.Column(
            "experience_paths_read",
            postgresql.ARRAY(sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "pointers_retrieved",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "workspace_actions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        # Output
        sa.Column("maestro_response", sa.Text(), nullable=False),
        sa.Column("response_model", sa.Text(), nullable=False),
        sa.Column("response_latency_ms", sa.Integer(), nullable=True),
        sa.Column("token_count_input", sa.Integer(), nullable=True),
        sa.Column("token_count_output", sa.Integer(), nullable=True),
        # Learning evaluation (filled async by Learning agent)
        sa.Column(
            "learning_assessment",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "scoring_dimensions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "experience_updates",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "knowledge_edits",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        # User signals (filled from subsequent interaction)
        sa.Column("user_followed_up", sa.Boolean(), nullable=True),
        sa.Column("user_corrected", sa.Boolean(), nullable=True),
        sa.Column("user_rephrased", sa.Boolean(), nullable=True),
        sa.Column("user_moved_on", sa.Boolean(), nullable=True),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # Indexes for common queries
    op.create_index(
        "idx_benchmark_project",
        "benchmark_logs",
        ["project_id"],
    )
    op.create_index(
        "idx_benchmark_session",
        "benchmark_logs",
        ["session_id"],
    )
    op.create_index(
        "idx_benchmark_model",
        "benchmark_logs",
        ["response_model"],
    )
    op.create_index(
        "idx_benchmark_created",
        "benchmark_logs",
        ["created_at"],
    )


def downgrade() -> None:
    """Drop benchmark_logs table."""
    op.drop_index("idx_benchmark_created", table_name="benchmark_logs")
    op.drop_index("idx_benchmark_model", table_name="benchmark_logs")
    op.drop_index("idx_benchmark_session", table_name="benchmark_logs")
    op.drop_index("idx_benchmark_project", table_name="benchmark_logs")
    op.drop_table("benchmark_logs")
