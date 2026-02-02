"""Add job_type column to processing_jobs table.

Revision ID: b1c2d3e4f5g6
Revises: a9b0c1d2e3f4
Create Date: 2026-02-02 14:00:00.000000

"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b1c2d3e4f5g6"
down_revision: str | None = "a9b0c1d2e3f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add job_type column to processing_jobs table."""
    op.add_column(
        "processing_jobs",
        sa.Column("job_type", sa.String(20), nullable=False, server_default="brain_mode"),
    )
    # Remove server_default after column is added (cleaner schema)
    op.alter_column("processing_jobs", "job_type", server_default=None)


def downgrade() -> None:
    """Remove job_type column from processing_jobs table."""
    op.drop_column("processing_jobs", "job_type")
