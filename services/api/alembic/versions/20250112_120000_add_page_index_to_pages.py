"""Add page_index column to pages table for multi-page PDF support.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2025-01-12 12:00:00.000000

"""
from typing import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: str | None = 'd4e5f6a7b8c9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add page_index column to pages table.

    This column stores the zero-based index of the page within a multi-page PDF.
    For single-page PDFs, this will be 0.
    For multi-page PDFs, each page gets its own Page record with a unique index.
    """
    op.add_column(
        'pages',
        sa.Column('page_index', sa.Integer(), nullable=False, server_default='0')
    )


def downgrade() -> None:
    """Remove page_index column from pages table."""
    op.drop_column('pages', 'page_index')
