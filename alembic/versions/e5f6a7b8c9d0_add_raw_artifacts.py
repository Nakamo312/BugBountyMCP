"""Add raw artifact index table

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-05-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'raw_artifacts',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('program_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('job_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('run_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('node_id', sa.String(length=100), nullable=False),
        sa.Column('event_name', sa.String(length=150), nullable=False),
        sa.Column('artifact_type', sa.String(length=50), nullable=False),
        sa.Column('storage_uri', sa.Text(), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('artifact_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['program_id'], ['programs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("artifact_type != ''", name='ck_raw_artifacts_type_not_empty'),
        sa.CheckConstraint("storage_uri != ''", name='ck_raw_artifacts_storage_uri_not_empty'),
        sa.CheckConstraint("size_bytes >= 0", name='ck_raw_artifacts_size_non_negative'),
    )
    op.create_index('ix_raw_artifacts_program_id', 'raw_artifacts', ['program_id'])
    op.create_index('ix_raw_artifacts_job_id', 'raw_artifacts', ['job_id'])
    op.create_index('ix_raw_artifacts_run_id', 'raw_artifacts', ['run_id'])
    op.create_index('ix_raw_artifacts_node_id', 'raw_artifacts', ['node_id'])
    op.create_index('ix_raw_artifacts_event_name', 'raw_artifacts', ['event_name'])
    op.create_index('idx_raw_artifacts_program_created', 'raw_artifacts', ['program_id', 'created_at'])
    op.create_index('idx_raw_artifacts_run', 'raw_artifacts', ['run_id'])


def downgrade() -> None:
    op.drop_index('idx_raw_artifacts_run', table_name='raw_artifacts')
    op.drop_index('idx_raw_artifacts_program_created', table_name='raw_artifacts')
    op.drop_index('ix_raw_artifacts_event_name', table_name='raw_artifacts')
    op.drop_index('ix_raw_artifacts_node_id', table_name='raw_artifacts')
    op.drop_index('ix_raw_artifacts_run_id', table_name='raw_artifacts')
    op.drop_index('ix_raw_artifacts_job_id', table_name='raw_artifacts')
    op.drop_index('ix_raw_artifacts_program_id', table_name='raw_artifacts')
    op.drop_table('raw_artifacts')
