"""Add page_embedding vector column to pages table.

Revision ID: f7a8b9c0d1e2
Revises: f6a7b8c9d0e1
Create Date: 2026-01-31 13:00:00.000000

"""
from typing import Sequence

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision: str = "f7a8b9c0d1e2"
down_revision: str | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add page_embedding column to pages table."""
    op.add_column(
        "pages",
        sa.Column("page_embedding", Vector(1024), nullable=True),
    )


def downgrade() -> None:
    """Remove page_embedding column from pages table."""
    op.drop_column("pages", "page_embedding")
