"""Add hidden column to queries table for soft delete.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2025-01-02 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: str | None = 'a1b2c3d4e5f6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add hidden column to queries table.

    This column enables soft delete - queries are hidden from UI but kept in DB.
    """
    op.add_column(
        'queries',
        sa.Column('hidden', sa.Boolean(), nullable=False, server_default='false')
    )


def downgrade() -> None:
    """Remove hidden column from queries table."""
    op.drop_column('queries', 'hidden')
