"""Add rejected action status

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-05-20

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        'ck_action_requests_status_valid',
        'action_requests',
        type_='check',
    )
    op.create_check_constraint(
        'ck_action_requests_status_valid',
        'action_requests',
        "status IN ('allowed', 'blocked', 'requires_approval', 'queued', 'rejected')",
    )
    op.drop_constraint(
        'ck_policy_decisions_status_valid',
        'policy_decisions',
        type_='check',
    )
    op.create_check_constraint(
        'ck_policy_decisions_status_valid',
        'policy_decisions',
        "status IN ('allowed', 'blocked', 'requires_approval', 'rejected')",
    )


def downgrade() -> None:
    op.drop_constraint(
        'ck_policy_decisions_status_valid',
        'policy_decisions',
        type_='check',
    )
    op.create_check_constraint(
        'ck_policy_decisions_status_valid',
        'policy_decisions',
        "status IN ('allowed', 'blocked', 'requires_approval')",
    )
    op.drop_constraint(
        'ck_action_requests_status_valid',
        'action_requests',
        type_='check',
    )
    op.create_check_constraint(
        'ck_action_requests_status_valid',
        'action_requests',
        "status IN ('allowed', 'blocked', 'requires_approval', 'queued')",
    )
