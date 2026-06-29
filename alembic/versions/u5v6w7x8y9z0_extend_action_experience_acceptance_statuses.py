"""Extend action experience proposal acceptance statuses.

Revision ID: u5v6w7x8y9z0
Revises: f9a0b1c2d3e4
"""

from alembic import op


revision = "u5v6w7x8y9z0"
down_revision = "f9a0b1c2d3e4"
branch_labels = None
depends_on = None


OLD_STATUSES = "('pending', 'accepted', 'rejected', 'suppressed', 'expired')"
NEW_STATUSES = "('pending', 'accepting', 'accepted', 'accept_failed', 'rejected', 'suppressed', 'expired')"


def upgrade() -> None:
    op.drop_constraint(
        "ck_action_experience_proposals_status_valid",
        "action_experience_proposals",
        type_="check",
    )
    op.create_check_constraint(
        "ck_action_experience_proposals_status_valid",
        "action_experience_proposals",
        f"status IN {NEW_STATUSES}",
    )


def downgrade() -> None:
    op.execute("UPDATE action_experience_proposals SET status = 'pending' WHERE status = 'accepting'")
    op.execute("UPDATE action_experience_proposals SET status = 'expired' WHERE status = 'accept_failed'")
    op.drop_constraint(
        "ck_action_experience_proposals_status_valid",
        "action_experience_proposals",
        type_="check",
    )
    op.create_check_constraint(
        "ck_action_experience_proposals_status_valid",
        "action_experience_proposals",
        f"status IN {OLD_STATUSES}",
    )
