"""Accept agent action proposals through ActionService.

Revision ID: r3s4t5u6v7w8
Revises: q2r3s4t5u6v7
Create Date: 2026-06-26
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

UUID = postgresql.UUID(as_uuid=True)


revision = "r3s4t5u6v7w8"
down_revision = "q2r3s4t5u6v7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_action_proposals",
        sa.Column("accepted_action_id", UUID, nullable=True),
    )
    op.add_column(
        "agent_action_proposals",
        sa.Column("accepted_by", sa.String(length=150), nullable=True),
    )
    op.add_column(
        "agent_action_proposals",
        sa.Column("accepted_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "agent_action_proposals",
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_agent_action_proposals_accepted_action_id",
        "agent_action_proposals",
        "action_requests",
        ["accepted_action_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_agent_action_proposals_accepted_action_id",
        "agent_action_proposals",
        ["accepted_action_id"],
    )
    op.create_check_constraint(
        "ck_agent_action_proposals_accepted_by_not_empty",
        "agent_action_proposals",
        "accepted_by IS NULL OR accepted_by != ''",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_agent_action_proposals_accepted_by_not_empty",
        "agent_action_proposals",
        type_="check",
    )
    op.drop_index(
        "ix_agent_action_proposals_accepted_action_id",
        table_name="agent_action_proposals",
    )
    op.drop_constraint(
        "fk_agent_action_proposals_accepted_action_id",
        "agent_action_proposals",
        type_="foreignkey",
    )
    op.drop_column("agent_action_proposals", "accepted_at")
    op.drop_column("agent_action_proposals", "accepted_reason")
    op.drop_column("agent_action_proposals", "accepted_by")
    op.drop_column("agent_action_proposals", "accepted_action_id")
