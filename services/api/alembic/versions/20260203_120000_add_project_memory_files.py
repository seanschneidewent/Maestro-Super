"""Add project_memory_files table for Big Maestro learning system.

Revision ID: 20260203_120000
Revises: 20260203_090000_add_sheet_card_to_pages
Create Date: 2026-02-03 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260203_120000'
down_revision = 'c4d5e6f7a8b9'  # 20260203_090000_add_sheet_card_to_pages
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create project_memory_files table for Big Maestro memory system
    op.create_table(
        'project_memory_files',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=True),
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('file_type', sa.Text(), nullable=False),
        sa.Column('file_content', sa.Text(), server_default=''),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.CheckConstraint(
            "file_type IN ('core', 'routing', 'preferences', 'memory', 'learning', 'fast_context', 'med_context', 'deep_context')",
            name='valid_file_type'
        ),
        sa.UniqueConstraint('project_id', 'file_type', name='uq_project_memory_file_type'),
    )
    
    op.create_index(
        'idx_project_memory_files_lookup',
        'project_memory_files',
        ['project_id', 'file_type']
    )
    
    # Create learning_events table to log teaching interactions
    op.create_table(
        'learning_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=True),
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('event_type', sa.Text(), nullable=False),  # 'correction', 'teaching', 'clarification'
        sa.Column('classification', sa.Text(), nullable=True),  # 'routing', 'truth', 'preference', 'fast_behavior', etc.
        sa.Column('original_query', sa.Text(), nullable=True),
        sa.Column('original_response', sa.Text(), nullable=True),
        sa.Column('correction_text', sa.Text(), nullable=True),
        sa.Column('file_updated', sa.Text(), nullable=True),
        sa.Column('update_content', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )
    
    op.create_index(
        'idx_learning_events_project',
        'learning_events',
        ['project_id', 'created_at']
    )


def downgrade() -> None:
    op.drop_index('idx_learning_events_project', table_name='learning_events')
    op.drop_table('learning_events')
    op.drop_index('idx_project_memory_files_lookup', table_name='project_memory_files')
    op.drop_table('project_memory_files')
