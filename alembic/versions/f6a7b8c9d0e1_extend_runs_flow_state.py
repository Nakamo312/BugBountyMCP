"""Extend runs with lightweight flow state

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-05-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('runs', sa.Column('node_id', sa.String(length=100), nullable=True))
    op.add_column('runs', sa.Column('event_name', sa.String(length=150), nullable=True))
    op.add_column('runs', sa.Column('trigger_event_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('runs', sa.Column('error', sa.Text(), nullable=True))

    op.create_index('ix_runs_node_id', 'runs', ['node_id'])
    op.create_index('ix_runs_event_name', 'runs', ['event_name'])
    op.create_index('ix_runs_trigger_event_id', 'runs', ['trigger_event_id'])
    op.create_index('idx_runs_node_event_created', 'runs', ['node_id', 'event_name', 'created_at'])


def downgrade() -> None:
    op.drop_index('idx_runs_node_event_created', table_name='runs')
    op.drop_index('ix_runs_trigger_event_id', table_name='runs')
    op.drop_index('ix_runs_event_name', table_name='runs')
    op.drop_index('ix_runs_node_id', table_name='runs')

    op.drop_column('runs', 'error')
    op.drop_column('runs', 'trigger_event_id')
    op.drop_column('runs', 'event_name')
    op.drop_column('runs', 'node_id')
