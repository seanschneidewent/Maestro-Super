"""add_rls_policies

Revision ID: 5455e648c653
Revises: 1ad6b6a2813b
Create Date: 2025-12-30 08:29:42.047745

This migration enables Row Level Security (RLS) on PostgreSQL.
On SQLite (dev), this migration is a no-op.

RLS policies ensure users can only access their own data even if
app-layer filtering has a bug.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5455e648c653"
down_revision: Union[str, None] = "1ad6b6a2813b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Only run on PostgreSQL - SQLite doesn't support RLS
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return

    # Enable RLS on all user-data tables
    tables = [
        "projects",
        "project_files",
        "context_pointers",
        "page_contexts",
        "discipline_contexts",
        "queries",
        "usage_events",
    ]

    for table in tables:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")

    # ========================================
    # Direct user_id tables
    # ========================================

    # Projects - direct user_id access
    op.execute(
        """
        CREATE POLICY "Users see own projects" ON projects
        FOR ALL USING (
            user_id = current_setting('request.jwt.claims', true)::json->>'sub'
        )
        """
    )

    # Queries - direct user_id access
    op.execute(
        """
        CREATE POLICY "Users see own queries" ON queries
        FOR ALL USING (
            user_id = current_setting('request.jwt.claims', true)::json->>'sub'
        )
        """
    )

    # Usage events - direct user_id access
    op.execute(
        """
        CREATE POLICY "Users see own usage" ON usage_events
        FOR ALL USING (
            user_id = current_setting('request.jwt.claims', true)::json->>'sub'
        )
        """
    )

    # ========================================
    # Via project_id
    # ========================================

    # Project files - via project_id
    op.execute(
        """
        CREATE POLICY "Users see own files" ON project_files
        FOR ALL USING (
            project_id IN (
                SELECT id FROM projects
                WHERE user_id = current_setting('request.jwt.claims', true)::json->>'sub'
            )
        )
        """
    )

    # Discipline contexts - via project_id
    op.execute(
        """
        CREATE POLICY "Users see own discipline contexts" ON discipline_contexts
        FOR ALL USING (
            project_id IN (
                SELECT id FROM projects
                WHERE user_id = current_setting('request.jwt.claims', true)::json->>'sub'
            )
        )
        """
    )

    # ========================================
    # Via file_id -> project_id
    # ========================================

    # Context pointers - via file_id -> project_id
    op.execute(
        """
        CREATE POLICY "Users see own pointers" ON context_pointers
        FOR ALL USING (
            file_id IN (
                SELECT pf.id FROM project_files pf
                JOIN projects p ON pf.project_id = p.id
                WHERE p.user_id = current_setting('request.jwt.claims', true)::json->>'sub'
            )
        )
        """
    )

    # Page contexts - via file_id -> project_id
    op.execute(
        """
        CREATE POLICY "Users see own page contexts" ON page_contexts
        FOR ALL USING (
            file_id IN (
                SELECT pf.id FROM project_files pf
                JOIN projects p ON pf.project_id = p.id
                WHERE p.user_id = current_setting('request.jwt.claims', true)::json->>'sub'
            )
        )
        """
    )


def downgrade() -> None:
    # Only run on PostgreSQL
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return

    # Drop policies
    policies = [
        ("projects", "Users see own projects"),
        ("project_files", "Users see own files"),
        ("context_pointers", "Users see own pointers"),
        ("page_contexts", "Users see own page contexts"),
        ("discipline_contexts", "Users see own discipline contexts"),
        ("queries", "Users see own queries"),
        ("usage_events", "Users see own usage"),
    ]

    for table, policy_name in policies:
        op.execute(f'DROP POLICY IF EXISTS "{policy_name}" ON {table}')

    # Disable RLS
    tables = [
        "projects",
        "project_files",
        "context_pointers",
        "page_contexts",
        "discipline_contexts",
        "queries",
        "usage_events",
    ]

    for table in tables:
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
