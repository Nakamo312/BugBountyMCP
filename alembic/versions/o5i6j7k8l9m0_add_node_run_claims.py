"""Add node run claim fields

Revision ID: o5i6j7k8l9m0
Revises: n4i5j6k7l8m9
Create Date: 2026-06-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'o5i6j7k8l9m0'
down_revision: Union[str, None] = 'n4i5j6k7l8m9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('runs', sa.Column('claim_key', sa.String(length=64), nullable=True))
    op.add_column('runs', sa.Column('input_fingerprint', sa.String(length=64), nullable=True))
    op.add_column('runs', sa.Column('target_fingerprint', sa.String(length=64), nullable=True))
    op.add_column(
        'runs',
        sa.Column('execution_mode', sa.String(length=20), nullable=False, server_default='inline'),
    )
    op.add_column('runs', sa.Column('scanner_started_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('runs', sa.Column('terminal_outcome', sa.String(length=50), nullable=True))
    op.add_column(
        'runs',
        sa.Column('needs_reconcile', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column('runs', sa.Column('reconcile_reason', sa.Text(), nullable=True))

    op.create_unique_constraint('uq_runs_claim_key', 'runs', ['claim_key'])
    op.create_index('ix_runs_input_fingerprint', 'runs', ['input_fingerprint'])
    op.create_index('ix_runs_target_fingerprint', 'runs', ['target_fingerprint'])
    op.create_index('ix_runs_terminal_outcome', 'runs', ['terminal_outcome'])
    op.create_index('idx_runs_execution_mode_status', 'runs', ['execution_mode', 'status'])
    op.create_check_constraint(
        'ck_runs_claim_key_not_empty',
        'runs',
        "claim_key IS NULL OR claim_key != ''",
    )
    op.create_check_constraint(
        'ck_runs_execution_mode_valid',
        'runs',
        "execution_mode IN ('inline', 'scheduled')",
    )
    op.create_check_constraint(
        'ck_runs_terminal_outcome_valid',
        'runs',
        "terminal_outcome IS NULL OR terminal_outcome IN "
        "('completed', 'partial', 'tool_failed', 'skipped', 'policy_blocked')",
    )


def downgrade() -> None:
    op.drop_constraint('ck_runs_terminal_outcome_valid', 'runs', type_='check')
    op.drop_constraint('ck_runs_execution_mode_valid', 'runs', type_='check')
    op.drop_constraint('ck_runs_claim_key_not_empty', 'runs', type_='check')
    op.drop_index('idx_runs_execution_mode_status', table_name='runs')
    op.drop_index('ix_runs_terminal_outcome', table_name='runs')
    op.drop_index('ix_runs_target_fingerprint', table_name='runs')
    op.drop_index('ix_runs_input_fingerprint', table_name='runs')
    op.drop_constraint('uq_runs_claim_key', 'runs', type_='unique')
    op.drop_column('runs', 'reconcile_reason')
    op.drop_column('runs', 'needs_reconcile')
    op.drop_column('runs', 'terminal_outcome')
    op.drop_column('runs', 'scanner_started_at')
    op.drop_column('runs', 'execution_mode')
    op.drop_column('runs', 'target_fingerprint')
    op.drop_column('runs', 'input_fingerprint')
    op.drop_column('runs', 'claim_key')
