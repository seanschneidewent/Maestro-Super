"""Add project_memory_files table for Big Maestro learning system.

NOTE: This migration was already applied. File exists as stub for Alembic history.
Big Maestro is on hold - tables exist but are unused.

Revision ID: 20260203_120000
Revises: c4d5e6f7a8b9
Create Date: 2026-02-03 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260203_120000'
down_revision = 'c4d5e6f7a8b9'  # 20260203_090000_add_sheet_card_to_pages
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Tables already exist from previous deploy - no-op
    pass


def downgrade() -> None:
    # Keep tables for now - Big Maestro on hold
    pass
