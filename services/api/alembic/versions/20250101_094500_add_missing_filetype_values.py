"""Add missing FileType enum values (CSV, MODEL, FOLDER).

Revision ID: 8a7b6c5d4e3f
Revises: 5455e648c653
Create Date: 2025-01-01 09:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8a7b6c5d4e3f'
down_revision: str | None = '5455e648c653'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add missing FileType enum values to project_files table.

    The initial migration only included PDF and IMAGE.
    We need to add CSV, MODEL, and FOLDER.

    With native_enum=False, SQLAlchemy stores enums as VARCHAR with a CHECK constraint.
    We need to drop the old constraint and add a new one with all values.
    """
    # For PostgreSQL with non-native enum (VARCHAR + CHECK constraint)
    # Drop the old constraint and add new one with all values
    op.execute("""
        ALTER TABLE project_files
        DROP CONSTRAINT IF EXISTS "ck_project_files_file_type_filetype";
    """)

    # Also try the auto-generated constraint name format
    op.execute("""
        ALTER TABLE project_files
        DROP CONSTRAINT IF EXISTS "project_files_file_type_check";
    """)

    # Add new constraint with all FileType values
    op.execute("""
        ALTER TABLE project_files
        ADD CONSTRAINT "project_files_file_type_check"
        CHECK (file_type IN ('PDF', 'IMAGE', 'CSV', 'MODEL', 'FOLDER'));
    """)


def downgrade() -> None:
    """Revert to original enum values (PDF, IMAGE only)."""
    op.execute("""
        ALTER TABLE project_files
        DROP CONSTRAINT IF EXISTS "project_files_file_type_check";
    """)

    op.execute("""
        ALTER TABLE project_files
        ADD CONSTRAINT "project_files_file_type_check"
        CHECK (file_type IN ('PDF', 'IMAGE'));
    """)
