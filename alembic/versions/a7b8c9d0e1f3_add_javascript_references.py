"""add javascript references

Revision ID: a7b8c9d0e1f3
Revises: c9d0e1f2g3h4
Create Date: 2026-06-16 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'a7b8c9d0e1f3'
down_revision = 'c9d0e1f2g3h4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'javascript_references',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('program_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('endpoint_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('service_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('job_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('run_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('correlation_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('raw_artifact_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('source_url', sa.Text(), nullable=False),
        sa.Column('referenced_url', sa.Text(), nullable=False),
        sa.Column('reference_type', sa.String(length=100), server_default='endpoint', nullable=False),
        sa.Column('source_tool', sa.String(length=100), nullable=False),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('observed_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("source_url != ''", name='ck_javascript_references_source_url_not_empty'),
        sa.CheckConstraint("referenced_url != ''", name='ck_javascript_references_referenced_url_not_empty'),
        sa.CheckConstraint("reference_type != ''", name='ck_javascript_references_reference_type_not_empty'),
        sa.CheckConstraint("source_tool != ''", name='ck_javascript_references_source_tool_not_empty'),
        sa.ForeignKeyConstraint(['endpoint_id'], ['endpoints.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['program_id'], ['programs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['raw_artifact_id'], ['raw_artifacts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['run_id'], ['runs.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['service_id'], ['services.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_javascript_references_program_id', 'javascript_references', ['program_id'])
    op.create_index('ix_javascript_references_endpoint_id', 'javascript_references', ['endpoint_id'])
    op.create_index('ix_javascript_references_service_id', 'javascript_references', ['service_id'])
    op.create_index('ix_javascript_references_job_id', 'javascript_references', ['job_id'])
    op.create_index('ix_javascript_references_run_id', 'javascript_references', ['run_id'])
    op.create_index('ix_javascript_references_correlation_id', 'javascript_references', ['correlation_id'])
    op.create_index('ix_javascript_references_raw_artifact_id', 'javascript_references', ['raw_artifact_id'])
    op.create_index('idx_javascript_references_program_observed', 'javascript_references', ['program_id', 'observed_at'])
    op.create_index('idx_javascript_references_endpoint_observed', 'javascript_references', ['endpoint_id', 'observed_at'])
    op.create_index('idx_javascript_references_run_observed', 'javascript_references', ['run_id', 'observed_at'])
    op.create_index(
        'uq_javascript_references_source_target_artifact',
        'javascript_references',
        ['program_id', 'raw_artifact_id', 'source_url', 'referenced_url'],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index('uq_javascript_references_source_target_artifact', table_name='javascript_references')
    op.drop_index('idx_javascript_references_run_observed', table_name='javascript_references')
    op.drop_index('idx_javascript_references_endpoint_observed', table_name='javascript_references')
    op.drop_index('idx_javascript_references_program_observed', table_name='javascript_references')
    op.drop_index('ix_javascript_references_raw_artifact_id', table_name='javascript_references')
    op.drop_index('ix_javascript_references_correlation_id', table_name='javascript_references')
    op.drop_index('ix_javascript_references_run_id', table_name='javascript_references')
    op.drop_index('ix_javascript_references_job_id', table_name='javascript_references')
    op.drop_index('ix_javascript_references_service_id', table_name='javascript_references')
    op.drop_index('ix_javascript_references_endpoint_id', table_name='javascript_references')
    op.drop_index('ix_javascript_references_program_id', table_name='javascript_references')
    op.drop_table('javascript_references')
