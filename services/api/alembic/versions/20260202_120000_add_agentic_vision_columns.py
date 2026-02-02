"""Add Agentic Vision columns to pages table.

Revision ID: a9b0c1d2e3f4
Revises: f7a8b9c0d1e2
Create Date: 2026-02-02 12:00:00.000000

"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "a9b0c1d2e3f4"
down_revision: str | None = "f7a8b9c0d1e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add Agentic Vision result columns to pages table."""
    op.add_column("pages", sa.Column("sheet_info", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("pages", sa.Column("master_index", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("pages", sa.Column("questions_answered", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("pages", sa.Column("processing_time_ms", sa.Integer(), nullable=True))
    op.add_column("pages", sa.Column("processing_error", sa.Text(), nullable=True))


def downgrade() -> None:
    """Remove Agentic Vision result columns from pages table."""
    op.drop_column("pages", "processing_error")
    op.drop_column("pages", "processing_time_ms")
    op.drop_column("pages", "questions_answered")
    op.drop_column("pages", "master_index")
    op.drop_column("pages", "sheet_info")
