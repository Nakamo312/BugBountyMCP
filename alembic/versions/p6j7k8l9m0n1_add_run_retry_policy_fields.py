"""Add run retry scheduling fields

Revision ID: p6j7k8l9m0n1
Revises: o5i6j7k8l9m0
Create Date: 2026-06-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'p6j7k8l9m0n1'
down_revision: Union[str, None] = 'o5i6j7k8l9m0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('runs', sa.Column('next_retry_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('runs', sa.Column('retry_reason', sa.String(length=100), nullable=True))
    op.create_index('ix_runs_next_retry_at', 'runs', ['next_retry_at'])


def downgrade() -> None:
    op.drop_index('ix_runs_next_retry_at', table_name='runs')
    op.drop_column('runs', 'retry_reason')
    op.drop_column('runs', 'next_retry_at')
