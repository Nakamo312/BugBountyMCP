"""Add orchestration state tables

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-05-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'action_requests',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('program_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('kind', sa.String(length=50), nullable=False),
        sa.Column('capability_id', sa.String(length=100), nullable=False),
        sa.Column('profile_id', sa.String(length=100), nullable=False),
        sa.Column('requested_by', sa.String(length=100), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('request', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['program_id'], ['programs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            "status IN ('allowed', 'blocked', 'requires_approval', 'queued')",
            name='ck_action_requests_status_valid',
        ),
    )
    op.create_index('ix_action_requests_program_id', 'action_requests', ['program_id'])
    op.create_index('ix_action_requests_capability_id', 'action_requests', ['capability_id'])
    op.create_index('ix_action_requests_profile_id', 'action_requests', ['profile_id'])
    op.create_index('ix_action_requests_status', 'action_requests', ['status'])
    op.create_index('idx_action_requests_program_status', 'action_requests', ['program_id', 'status'])

    op.create_table(
        'policy_decisions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('action_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('reasons', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('allowed_targets', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('blocked_targets', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['action_id'], ['action_requests.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            "status IN ('allowed', 'blocked', 'requires_approval')",
            name='ck_policy_decisions_status_valid',
        ),
    )
    op.create_index('ix_policy_decisions_action_id', 'policy_decisions', ['action_id'])
    op.create_index('ix_policy_decisions_status', 'policy_decisions', ['status'])

    op.create_table(
        'jobs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('action_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('program_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('capability_id', sa.String(length=100), nullable=False),
        sa.Column('profile_id', sa.String(length=100), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('correlation_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['action_id'], ['action_requests.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['program_id'], ['programs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'cancelled')",
            name='ck_jobs_status_valid',
        ),
    )
    op.create_index('ix_jobs_action_id', 'jobs', ['action_id'])
    op.create_index('ix_jobs_program_id', 'jobs', ['program_id'])
    op.create_index('ix_jobs_capability_id', 'jobs', ['capability_id'])
    op.create_index('ix_jobs_profile_id', 'jobs', ['profile_id'])
    op.create_index('ix_jobs_status', 'jobs', ['status'])
    op.create_index('ix_jobs_correlation_id', 'jobs', ['correlation_id'])
    op.create_index('idx_jobs_program_status', 'jobs', ['program_id', 'status'])

    op.create_table(
        'runs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('job_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('program_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('attempt', sa.Integer(), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['program_id'], ['programs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint('attempt > 0', name='ck_runs_attempt_positive'),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'cancelled')",
            name='ck_runs_status_valid',
        ),
    )
    op.create_index('ix_runs_job_id', 'runs', ['job_id'])
    op.create_index('ix_runs_program_id', 'runs', ['program_id'])
    op.create_index('ix_runs_status', 'runs', ['status'])
    op.create_index('idx_runs_program_status', 'runs', ['program_id', 'status'])

    op.create_table(
        'event_store',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('event_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('event_type', sa.String(length=150), nullable=False),
        sa.Column('program_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('job_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('run_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('correlation_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('causation_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('source', sa.String(length=100), nullable=False),
        sa.Column('profile', sa.String(length=100), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['program_id'], ['programs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('event_id'),
    )
    op.create_index('ix_event_store_event_id', 'event_store', ['event_id'])
    op.create_index('ix_event_store_event_type', 'event_store', ['event_type'])
    op.create_index('ix_event_store_program_id', 'event_store', ['program_id'])
    op.create_index('ix_event_store_job_id', 'event_store', ['job_id'])
    op.create_index('ix_event_store_run_id', 'event_store', ['run_id'])
    op.create_index('ix_event_store_correlation_id', 'event_store', ['correlation_id'])
    op.create_index('ix_event_store_causation_id', 'event_store', ['causation_id'])
    op.create_index('idx_event_store_program_type_created', 'event_store', ['program_id', 'event_type', 'created_at'])


def downgrade() -> None:
    op.drop_index('idx_event_store_program_type_created', table_name='event_store')
    op.drop_index('ix_event_store_causation_id', table_name='event_store')
    op.drop_index('ix_event_store_correlation_id', table_name='event_store')
    op.drop_index('ix_event_store_run_id', table_name='event_store')
    op.drop_index('ix_event_store_job_id', table_name='event_store')
    op.drop_index('ix_event_store_program_id', table_name='event_store')
    op.drop_index('ix_event_store_event_type', table_name='event_store')
    op.drop_index('ix_event_store_event_id', table_name='event_store')
    op.drop_table('event_store')

    op.drop_index('idx_runs_program_status', table_name='runs')
    op.drop_index('ix_runs_status', table_name='runs')
    op.drop_index('ix_runs_program_id', table_name='runs')
    op.drop_index('ix_runs_job_id', table_name='runs')
    op.drop_table('runs')

    op.drop_index('idx_jobs_program_status', table_name='jobs')
    op.drop_index('ix_jobs_correlation_id', table_name='jobs')
    op.drop_index('ix_jobs_status', table_name='jobs')
    op.drop_index('ix_jobs_profile_id', table_name='jobs')
    op.drop_index('ix_jobs_capability_id', table_name='jobs')
    op.drop_index('ix_jobs_program_id', table_name='jobs')
    op.drop_index('ix_jobs_action_id', table_name='jobs')
    op.drop_table('jobs')

    op.drop_index('ix_policy_decisions_status', table_name='policy_decisions')
    op.drop_index('ix_policy_decisions_action_id', table_name='policy_decisions')
    op.drop_table('policy_decisions')

    op.drop_index('idx_action_requests_program_status', table_name='action_requests')
    op.drop_index('ix_action_requests_status', table_name='action_requests')
    op.drop_index('ix_action_requests_profile_id', table_name='action_requests')
    op.drop_index('ix_action_requests_capability_id', table_name='action_requests')
    op.drop_index('ix_action_requests_program_id', table_name='action_requests')
    op.drop_table('action_requests')
