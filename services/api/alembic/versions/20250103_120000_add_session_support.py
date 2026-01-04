"""Add session support for query grouping.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2025-01-03 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: str | None = 'b2c3d4e5f6a7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add sessions table, update queries, and create query_pages junction table."""

    # Create sessions table
    op.create_table(
        'sessions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=255), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('sessions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_sessions_project_id'), ['project_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_sessions_user_id'), ['user_id'], unique=False)

    # Add columns to queries table
    with op.batch_alter_table('queries', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('session_id', sa.String(length=36), nullable=True)
        )
        batch_op.add_column(
            sa.Column('display_title', sa.String(length=100), nullable=True)
        )
        batch_op.add_column(
            sa.Column('sequence_order', sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            'fk_queries_session_id',
            'sessions',
            ['session_id'],
            ['id'],
            ondelete='SET NULL'
        )
        batch_op.create_index(batch_op.f('ix_queries_session_id'), ['session_id'], unique=False)

    # Create query_pages junction table
    op.create_table(
        'query_pages',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('query_id', sa.String(length=36), nullable=False),
        sa.Column('page_id', sa.String(length=36), nullable=False),
        sa.Column('page_order', sa.Integer(), nullable=False),
        sa.Column('pointers_shown', sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql'), nullable=True),
        sa.ForeignKeyConstraint(['query_id'], ['queries.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['page_id'], ['pages.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('query_pages', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_query_pages_query_id'), ['query_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_query_pages_page_id'), ['page_id'], unique=False)


def downgrade() -> None:
    """Remove session support."""

    # Drop query_pages table
    with op.batch_alter_table('query_pages', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_query_pages_page_id'))
        batch_op.drop_index(batch_op.f('ix_query_pages_query_id'))
    op.drop_table('query_pages')

    # Remove columns from queries table
    with op.batch_alter_table('queries', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_queries_session_id'))
        batch_op.drop_constraint('fk_queries_session_id', type_='foreignkey')
        batch_op.drop_column('sequence_order')
        batch_op.drop_column('display_title')
        batch_op.drop_column('session_id')

    # Drop sessions table
    with op.batch_alter_table('sessions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_sessions_user_id'))
        batch_op.drop_index(batch_op.f('ix_sessions_project_id'))
    op.drop_table('sessions')
