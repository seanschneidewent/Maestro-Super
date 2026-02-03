"""Add sheet_card JSONB column to pages table.

Revision ID: c4d5e6f7a8b9
Revises: b1c2d3e4f5g6
Create Date: 2026-02-03 09:00:00.000000

"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "c4d5e6f7a8b9"
down_revision: str | None = "b1c2d3e4f5g6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add reflection-first sheet card storage column."""
    op.add_column("pages", sa.Column("sheet_card", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    """Remove reflection-first sheet card storage column."""
    op.drop_column("pages", "sheet_card")

