"""Add Brain Mode fields to pages table.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-01-31 12:00:00.000000

"""
from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add Brain Mode fields to pages table."""
    op.add_column("pages", sa.Column("regions", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("pages", sa.Column("sheet_reflection", sa.Text(), nullable=True))
    op.add_column("pages", sa.Column("page_type", sa.String(length=50), nullable=True))
    op.add_column("pages", sa.Column("cross_references", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    """Remove Brain Mode fields from pages table."""
    op.drop_column("pages", "cross_references")
    op.drop_column("pages", "page_type")
    op.drop_column("pages", "sheet_reflection")
    op.drop_column("pages", "regions")
