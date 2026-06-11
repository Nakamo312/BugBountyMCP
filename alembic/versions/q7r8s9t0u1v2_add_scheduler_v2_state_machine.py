"""Add scheduler V2 state machine fields

Revision ID: q7r8s9t0u1v2
Revises: p6j7k8l9m0n1
Create Date: 2026-06-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'q7r8s9t0u1v2'
down_revision: Union[str, None] = 'p6j7k8l9m0n1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('runs', sa.Column('leased_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('runs', sa.Column('lease_owner', sa.String(length=100), nullable=True))
    op.add_column('runs', sa.Column('lease_expires_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('runs', sa.Column('flushing_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('runs', sa.Column('next_run_at', sa.DateTime(timezone=True), nullable=True))

    op.drop_constraint('ck_runs_status_valid', 'runs', type_='check')
    op.create_check_constraint(
        'ck_runs_status_valid',
        'runs',
        "status IN ('queued', 'leased', 'running', 'flushing', 'completed', 'failed', 'dead', 'cancelled')",
    )
    op.create_index(
        'idx_runs_scheduled_ready_node_next_run_created',
        'runs',
        ['node_id', 'next_run_at', 'created_at', 'id'],
        postgresql_where=sa.text(
            "execution_mode = 'scheduled' "
            "AND status = 'queued' "
            "AND terminal_outcome IS NULL "
            "AND needs_reconcile = false"
        ),
    )
    op.create_index(
        'idx_runs_scheduled_lease_expiry',
        'runs',
        ['lease_expires_at', 'id'],
        postgresql_where=sa.text(
            "execution_mode = 'scheduled' "
            "AND status = 'leased'"
        ),
    )


def downgrade() -> None:
    op.drop_index('idx_runs_scheduled_lease_expiry', table_name='runs')
    op.drop_index('idx_runs_scheduled_ready_node_next_run_created', table_name='runs')
    op.drop_constraint('ck_runs_status_valid', 'runs', type_='check')
    op.create_check_constraint(
        'ck_runs_status_valid',
        'runs',
        "status IN ('queued', 'running', 'completed', 'failed', 'cancelled')",
    )

    op.drop_column('runs', 'next_run_at')
    op.drop_column('runs', 'flushing_at')
    op.drop_column('runs', 'lease_expires_at')
    op.drop_column('runs', 'lease_owner')
    op.drop_column('runs', 'leased_at')
