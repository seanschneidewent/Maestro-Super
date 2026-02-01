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
    """Add page_embedding column to pages table with IVFFlat index."""
    op.add_column(
        "pages",
        sa.Column("page_embedding", Vector(1024), nullable=True),
    )

    # Create IVFFlat index for efficient vector similarity search.
    # IVFFlat requires at least some data to build clusters, so we use
    # IF NOT EXISTS and a reasonable number of lists (100 is good for <1M rows).
    # The index uses cosine distance (vector_cosine_ops) for semantic similarity.
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_pages_page_embedding_ivfflat
        ON pages
        USING ivfflat (page_embedding vector_cosine_ops)
        WITH (lists = 100);
        """
    )


def downgrade() -> None:
    """Remove page_embedding column and index from pages table."""
    op.execute("DROP INDEX IF EXISTS ix_pages_page_embedding_ivfflat;")
    op.drop_column("pages", "page_embedding")
