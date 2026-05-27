"""Add HTTP observation tables

Revision ID: g7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-05-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'g7b8c9d0e1f2'
down_revision: Union[str, None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'http_observations',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('program_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('endpoint_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('service_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('job_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('run_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('correlation_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('raw_artifact_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('method', sa.String(length=10), nullable=False),
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column('status_code', sa.Integer(), nullable=True),
        sa.Column('content_type', sa.Text(), nullable=True),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('body_sha256', sa.String(length=64), nullable=True),
        sa.Column('body_size_bytes', sa.Integer(), nullable=True),
        sa.Column('body_artifact_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('body_preview', sa.Text(), nullable=True),
        sa.Column('source_tool', sa.String(length=100), nullable=False),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('observed_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("method != ''", name='ck_http_observations_method_not_empty'),
        sa.CheckConstraint("url != ''", name='ck_http_observations_url_not_empty'),
        sa.CheckConstraint("source_tool != ''", name='ck_http_observations_source_tool_not_empty'),
        sa.CheckConstraint(
            "status_code IS NULL OR (status_code >= 100 AND status_code <= 599)",
            name='ck_http_observations_status_code_range',
        ),
        sa.CheckConstraint(
            "body_size_bytes IS NULL OR body_size_bytes >= 0",
            name='ck_http_observations_body_size_non_negative',
        ),
        sa.ForeignKeyConstraint(['program_id'], ['programs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['endpoint_id'], ['endpoints.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['service_id'], ['services.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['run_id'], ['runs.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['raw_artifact_id'], ['raw_artifacts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['body_artifact_id'], ['raw_artifacts.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_http_observations_program_id', 'http_observations', ['program_id'])
    op.create_index('ix_http_observations_endpoint_id', 'http_observations', ['endpoint_id'])
    op.create_index('ix_http_observations_service_id', 'http_observations', ['service_id'])
    op.create_index('ix_http_observations_job_id', 'http_observations', ['job_id'])
    op.create_index('ix_http_observations_run_id', 'http_observations', ['run_id'])
    op.create_index('ix_http_observations_correlation_id', 'http_observations', ['correlation_id'])
    op.create_index('ix_http_observations_raw_artifact_id', 'http_observations', ['raw_artifact_id'])
    op.create_index('ix_http_observations_body_artifact_id', 'http_observations', ['body_artifact_id'])
    op.create_index('idx_http_observations_program_observed', 'http_observations', ['program_id', 'observed_at'])
    op.create_index('idx_http_observations_endpoint_observed', 'http_observations', ['endpoint_id', 'observed_at'])
    op.create_index('idx_http_observations_run_observed', 'http_observations', ['run_id', 'observed_at'])

    op.create_table(
        'http_observation_headers',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('observation_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('ordinal', sa.Integer(), nullable=False),
        sa.CheckConstraint("name != ''", name='ck_http_observation_headers_name_not_empty'),
        sa.CheckConstraint("ordinal >= 0", name='ck_http_observation_headers_ordinal_non_negative'),
        sa.ForeignKeyConstraint(['observation_id'], ['http_observations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_http_observation_headers_observation_id', 'http_observation_headers', ['observation_id'])
    op.create_index(
        'idx_http_observation_headers_lookup',
        'http_observation_headers',
        ['observation_id', 'name'],
    )


def downgrade() -> None:
    op.drop_index('idx_http_observation_headers_lookup', table_name='http_observation_headers')
    op.drop_index('ix_http_observation_headers_observation_id', table_name='http_observation_headers')
    op.drop_table('http_observation_headers')

    op.drop_index('idx_http_observations_run_observed', table_name='http_observations')
    op.drop_index('idx_http_observations_endpoint_observed', table_name='http_observations')
    op.drop_index('idx_http_observations_program_observed', table_name='http_observations')
    op.drop_index('ix_http_observations_body_artifact_id', table_name='http_observations')
    op.drop_index('ix_http_observations_raw_artifact_id', table_name='http_observations')
    op.drop_index('ix_http_observations_correlation_id', table_name='http_observations')
    op.drop_index('ix_http_observations_run_id', table_name='http_observations')
    op.drop_index('ix_http_observations_job_id', table_name='http_observations')
    op.drop_index('ix_http_observations_service_id', table_name='http_observations')
    op.drop_index('ix_http_observations_endpoint_id', table_name='http_observations')
    op.drop_index('ix_http_observations_program_id', table_name='http_observations')
    op.drop_table('http_observations')
