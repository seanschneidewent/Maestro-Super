"""Add ocr_data JSONB column to pointers table.

Revision ID: 9b8c7d6e5f4a
Revises: 8a7b6c5d4e3f
Create Date: 2025-01-01 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = '9b8c7d6e5f4a'
down_revision: str | None = '8a7b6c5d4e3f'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add ocr_data column to pointers table.

    This column stores word-level OCR data with positions for highlighting:
    [{text: str, x: float, y: float, w: float, h: float, confidence: int}]
    Coordinates are normalized 0-1 relative to the cropped region.
    """
    op.add_column(
        'pointers',
        sa.Column('ocr_data', JSONB, nullable=True)
    )


def downgrade() -> None:
    """Remove ocr_data column from pointers table."""
    op.drop_column('pointers', 'ocr_data')
