"""V3 Schema Foundation — enrichment pipeline, experience files, sessions.

Adds:
- enrichment_status, cross_references, enrichment_metadata columns to pointers
- experience_files table (Learning's filesystem)
- sessions table (persistent Maestro sessions)
- Backfills enrichment_status based on existing data

Revision ID: v3_schema_001
Revises: 20260203_120000
Create Date: 2026-02-08 12:00:00.000000

"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "v3_schema_001"
down_revision: str | None = "20260203_120000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add V3 schema: pointer enrichment columns, experience_files, sessions."""

    # ──────────────────────────────────────────────────────────────
    # 1. Pointer enrichment columns
    # ──────────────────────────────────────────────────────────────
    op.add_column(
        "pointers",
        sa.Column(
            "enrichment_status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column(
        "pointers",
        sa.Column(
            "cross_references",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "pointers",
        sa.Column(
            "enrichment_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.create_index(
        "idx_pointers_enrichment_status",
        "pointers",
        ["enrichment_status"],
    )

    # Backfill: existing enriched pointers → 'complete'
    op.execute(
        "UPDATE pointers SET enrichment_status = 'complete' "
        "WHERE description IS NOT NULL AND description != '' AND embedding IS NOT NULL"
    )
    # Everything else stays 'pending' (the server_default)

    # ──────────────────────────────────────────────────────────────
    # 2. experience_files table
    # NOTE: Uses postgresql.UUID to match projects.id actual type in Supabase
    # ──────────────────────────────────────────────────────────────
    op.create_table(
        "experience_files",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("updated_by_session", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("project_id", "path", name="uq_experience_files_project_path"),
    )
    op.create_index("idx_experience_files_project", "experience_files", ["project_id"])

    # ──────────────────────────────────────────────────────────────
    # 3. sessions table
    # NOTE: Uses postgresql.UUID to match projects.id actual type in Supabase
    # ──────────────────────────────────────────────────────────────
    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("session_type", sa.String(20), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("workspace_name", sa.Text(), nullable=True),
        sa.Column(
            "maestro_messages",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "learning_messages",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "workspace_state",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            server_default='{"displayed_pages":[],"highlighted_pointers":[],"pinned_pages":[]}',
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "last_active_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "session_type IN ('workspace', 'telegram')",
            name="ck_sessions_session_type",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'idle', 'closed')",
            name="ck_sessions_status",
        ),
    )
    op.create_index("idx_sessions_project", "sessions", ["project_id"])
    op.create_index("idx_sessions_user", "sessions", ["user_id"])
    op.create_index(
        "idx_sessions_active",
        "sessions",
        ["status"],
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    """Remove V3 schema additions."""
    # Sessions
    op.drop_index("idx_sessions_active", table_name="sessions")
    op.drop_index("idx_sessions_user", table_name="sessions")
    op.drop_index("idx_sessions_project", table_name="sessions")
    op.drop_table("sessions")

    # Experience files
    op.drop_index("idx_experience_files_project", table_name="experience_files")
    op.drop_table("experience_files")

    # Pointer enrichment columns
    op.drop_index("idx_pointers_enrichment_status", table_name="pointers")
    op.drop_column("pointers", "enrichment_metadata")
    op.drop_column("pointers", "cross_references")
    op.drop_column("pointers", "enrichment_status")
