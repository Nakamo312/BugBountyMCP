"""Review agent action proposals as feedback.

Revision ID: s4t5u6v7w8x9
Revises: r3s4t5u6v7w8
Create Date: 2026-06-26
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

UUID = postgresql.UUID(as_uuid=True)


revision = "s4t5u6v7w8x9"
down_revision = "r3s4t5u6v7w8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_action_proposals", sa.Column("reviewed_by", sa.String(length=150), nullable=True))
    op.add_column("agent_action_proposals", sa.Column("review_reason", sa.Text(), nullable=True))
    op.add_column(
        "agent_action_proposals",
        sa.Column("review_feedback", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.add_column("agent_action_proposals", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("idx_agent_action_proposals_reviewed_by", "agent_action_proposals", ["reviewed_by"])
    op.create_check_constraint(
        "ck_agent_action_proposals_reviewed_by_not_empty",
        "agent_action_proposals",
        "reviewed_by IS NULL OR reviewed_by != ''",
    )

    op.create_table(
        "agent_action_proposal_feedback_events",
        sa.Column("id", UUID, nullable=False),
        sa.Column("proposal_id", UUID, nullable=False),
        sa.Column("program_id", UUID, nullable=False),
        sa.Column("campaign_id", UUID, nullable=True),
        sa.Column("task_id", UUID, nullable=False),
        sa.Column("source_message_id", UUID, nullable=False),
        sa.Column("agent_key", sa.String(length=100), nullable=False),
        sa.Column("previous_status", sa.String(length=30), nullable=False),
        sa.Column("new_status", sa.String(length=30), nullable=False),
        sa.Column("feedback_type", sa.String(length=40), nullable=False),
        sa.Column("actor", sa.String(length=150), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("feedback_tags", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["proposal_id"], ["agent_action_proposals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_id"], ["agent_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_message_id"], ["agent_task_messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("agent_key != ''", name="ck_agent_action_proposal_feedback_agent_not_empty"),
        sa.CheckConstraint("actor != ''", name="ck_agent_action_proposal_feedback_actor_not_empty"),
        sa.CheckConstraint(
            "feedback_type IN ('rejected', 'suppressed')",
            name="ck_agent_action_proposal_feedback_type_valid",
        ),
        sa.CheckConstraint(
            "new_status IN ('rejected', 'suppressed')",
            name="ck_agent_action_proposal_feedback_new_status_valid",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_agent_action_proposal_feedback_confidence_range",
        ),
    )
    op.create_index("ix_agent_action_proposal_feedback_events_proposal_id", "agent_action_proposal_feedback_events", ["proposal_id"])
    op.create_index("ix_agent_action_proposal_feedback_events_program_id", "agent_action_proposal_feedback_events", ["program_id"])
    op.create_index("ix_agent_action_proposal_feedback_events_campaign_id", "agent_action_proposal_feedback_events", ["campaign_id"])
    op.create_index("ix_agent_action_proposal_feedback_events_task_id", "agent_action_proposal_feedback_events", ["task_id"])
    op.create_index("ix_agent_action_proposal_feedback_events_source_message_id", "agent_action_proposal_feedback_events", ["source_message_id"])
    op.create_index("ix_agent_action_proposal_feedback_events_agent_key", "agent_action_proposal_feedback_events", ["agent_key"])
    op.create_index("ix_agent_action_proposal_feedback_events_feedback_type", "agent_action_proposal_feedback_events", ["feedback_type"])
    op.create_index("ix_agent_action_proposal_feedback_events_actor", "agent_action_proposal_feedback_events", ["actor"])
    op.create_index(
        "idx_agent_action_proposal_feedback_program_created",
        "agent_action_proposal_feedback_events",
        ["program_id", "created_at"],
    )
    op.create_index(
        "idx_agent_action_proposal_feedback_task_created",
        "agent_action_proposal_feedback_events",
        ["task_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_agent_action_proposal_feedback_task_created", table_name="agent_action_proposal_feedback_events")
    op.drop_index("idx_agent_action_proposal_feedback_program_created", table_name="agent_action_proposal_feedback_events")
    op.drop_index("ix_agent_action_proposal_feedback_events_actor", table_name="agent_action_proposal_feedback_events")
    op.drop_index("ix_agent_action_proposal_feedback_events_feedback_type", table_name="agent_action_proposal_feedback_events")
    op.drop_index("ix_agent_action_proposal_feedback_events_agent_key", table_name="agent_action_proposal_feedback_events")
    op.drop_index("ix_agent_action_proposal_feedback_events_source_message_id", table_name="agent_action_proposal_feedback_events")
    op.drop_index("ix_agent_action_proposal_feedback_events_task_id", table_name="agent_action_proposal_feedback_events")
    op.drop_index("ix_agent_action_proposal_feedback_events_campaign_id", table_name="agent_action_proposal_feedback_events")
    op.drop_index("ix_agent_action_proposal_feedback_events_program_id", table_name="agent_action_proposal_feedback_events")
    op.drop_index("ix_agent_action_proposal_feedback_events_proposal_id", table_name="agent_action_proposal_feedback_events")
    op.drop_table("agent_action_proposal_feedback_events")

    op.drop_constraint(
        "ck_agent_action_proposals_reviewed_by_not_empty",
        "agent_action_proposals",
        type_="check",
    )
    op.drop_index("idx_agent_action_proposals_reviewed_by", table_name="agent_action_proposals")
    op.drop_column("agent_action_proposals", "reviewed_at")
    op.drop_column("agent_action_proposals", "review_feedback")
    op.drop_column("agent_action_proposals", "review_reason")
    op.drop_column("agent_action_proposals", "reviewed_by")
