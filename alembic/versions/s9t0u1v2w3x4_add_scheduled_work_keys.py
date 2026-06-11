"""Add scheduled work keys for active exact dedup.

Revision ID: s9t0u1v2w3x4
Revises: r8s9t0u1v2w3
Create Date: 2026-06-09 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

from api.infrastructure.database.types import JSONType


revision = 's9t0u1v2w3x4'
down_revision = 'r8s9t0u1v2w3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('runs', sa.Column('work_key', sa.String(length=64), nullable=True))
    op.add_column('runs', sa.Column('coalesced_triggers', JSONType(), nullable=True))
    op.create_check_constraint(
        'ck_runs_work_key_not_empty',
        'runs',
        "work_key IS NULL OR work_key != ''",
    )
    op.create_index(
        'idx_runs_scheduled_active_work_key_unique',
        'runs',
        ['work_key'],
        unique=True,
        postgresql_where=sa.text(
            "execution_mode = 'scheduled' "
            "AND work_key IS NOT NULL "
            "AND status IN ('queued', 'leased', 'running', 'flushing') "
            "AND terminal_outcome IS NULL"
        ),
    )
    op.create_index(
        'idx_runs_scheduled_work_lookup',
        'runs',
        ['node_id', 'program_id', 'status', 'work_key'],
        unique=False,
        postgresql_where=sa.text(
            "execution_mode = 'scheduled' "
            "AND work_key IS NOT NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index('idx_runs_scheduled_work_lookup', table_name='runs')
    op.drop_index('idx_runs_scheduled_active_work_key_unique', table_name='runs')
    op.drop_constraint('ck_runs_work_key_not_empty', 'runs', type_='check')
    op.drop_column('runs', 'coalesced_triggers')
    op.drop_column('runs', 'work_key')
