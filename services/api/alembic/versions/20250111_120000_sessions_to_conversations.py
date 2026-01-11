"""Rename sessions to conversations and add title column.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2025-01-11 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: str | None = 'c3d4e5f6a7b8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Rename sessions to conversations and add title column."""

    # Step 1: Add title column to sessions table
    op.add_column('sessions', sa.Column('title', sa.Text(), nullable=True))

    # Step 2: Drop FK constraint and index on queries.session_id
    with op.batch_alter_table('queries', schema=None) as batch_op:
        batch_op.drop_index('ix_queries_session_id')
        batch_op.drop_constraint('fk_queries_session_id', type_='foreignkey')

    # Step 3: Rename session_id column to conversation_id
    op.alter_column('queries', 'session_id', new_column_name='conversation_id')

    # Step 4: Rename sessions table to conversations
    op.rename_table('sessions', 'conversations')

    # Step 5: Recreate FK constraint and index with new names
    with op.batch_alter_table('queries', schema=None) as batch_op:
        batch_op.create_foreign_key(
            'fk_queries_conversation_id',
            'conversations',
            ['conversation_id'],
            ['id'],
            ondelete='SET NULL'
        )
        batch_op.create_index('ix_queries_conversation_id', ['conversation_id'], unique=False)

    # Step 6: Update indexes on conversations table (rename from sessions prefix)
    # Note: We need to drop and recreate with new names
    with op.batch_alter_table('conversations', schema=None) as batch_op:
        batch_op.drop_index('ix_sessions_project_id')
        batch_op.drop_index('ix_sessions_user_id')
        batch_op.create_index('ix_conversations_project_id', ['project_id'], unique=False)
        batch_op.create_index('ix_conversations_user_id', ['user_id'], unique=False)


def downgrade() -> None:
    """Revert conversations back to sessions."""

    # Step 1: Rename indexes back
    with op.batch_alter_table('conversations', schema=None) as batch_op:
        batch_op.drop_index('ix_conversations_project_id')
        batch_op.drop_index('ix_conversations_user_id')
        batch_op.create_index('ix_sessions_project_id', ['project_id'], unique=False)
        batch_op.create_index('ix_sessions_user_id', ['user_id'], unique=False)

    # Step 2: Drop FK constraint and index on queries.conversation_id
    with op.batch_alter_table('queries', schema=None) as batch_op:
        batch_op.drop_index('ix_queries_conversation_id')
        batch_op.drop_constraint('fk_queries_conversation_id', type_='foreignkey')

    # Step 3: Rename conversations table back to sessions
    op.rename_table('conversations', 'sessions')

    # Step 4: Rename conversation_id column back to session_id
    op.alter_column('queries', 'conversation_id', new_column_name='session_id')

    # Step 5: Recreate original FK constraint and index
    with op.batch_alter_table('queries', schema=None) as batch_op:
        batch_op.create_foreign_key(
            'fk_queries_session_id',
            'sessions',
            ['session_id'],
            ['id'],
            ondelete='SET NULL'
        )
        batch_op.create_index('ix_queries_session_id', ['session_id'], unique=False)

    # Step 6: Drop title column
    op.drop_column('sessions', 'title')
