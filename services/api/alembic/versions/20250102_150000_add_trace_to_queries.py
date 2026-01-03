"""Add trace JSONB column to queries table.

Revision ID: a1b2c3d4e5f6
Revises: 9b8c7d6e5f4a
Create Date: 2025-01-02 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: str | None = '9b8c7d6e5f4a'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add trace column to queries table.

    This column stores the full execution trace for session restoration:
    [{type: 'reasoning'|'tool_call'|'tool_result', content?, tool?, input?, result?}]
    """
    op.add_column(
        'queries',
        sa.Column('trace', JSONB, nullable=True)
    )


def downgrade() -> None:
    """Remove trace column from queries table."""
    op.drop_column('queries', 'trace')
