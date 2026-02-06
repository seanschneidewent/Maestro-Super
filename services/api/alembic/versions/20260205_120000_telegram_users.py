"""Add telegram_users table for Telegram Mode.

Maps Telegram user IDs to Maestro user IDs and projects.

Revision ID: telegram_users_001
Revises: v3_schema_001
Create Date: 2026-02-05 12:00:00.000000

"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "telegram_users_001"
down_revision: str | None = "v3_schema_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create telegram_users table."""
    op.create_table(
        "telegram_users",
        sa.Column("telegram_user_id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("projects.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("idx_telegram_users_user_id", "telegram_users", ["user_id"])
    op.create_index("idx_telegram_users_project_id", "telegram_users", ["project_id"])


def downgrade() -> None:
    """Drop telegram_users table."""
    op.drop_index("idx_telegram_users_project_id", table_name="telegram_users")
    op.drop_index("idx_telegram_users_user_id", table_name="telegram_users")
    op.drop_table("telegram_users")
