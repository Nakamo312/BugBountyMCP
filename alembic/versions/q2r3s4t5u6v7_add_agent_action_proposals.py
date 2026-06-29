"""Persist bounded agent action proposals.

Revision ID: q2r3s4t5u6v7
Revises: p1q2r3s4t5u6
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "q2r3s4t5u6v7"
down_revision = "p1q2r3s4t5u6"
branch_labels = None
depends_on = None


PROPOSAL_TYPES = "('investigation_task', 'tool_action')"
PROPOSAL_STATUSES = "('pending', 'accepted', 'rejected', 'suppressed', 'expired')"


def upgrade() -> None:
    op.create_table(
        "agent_action_proposals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("program_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_key", sa.String(length=100), nullable=False),
        sa.Column("proposal_key", sa.String(length=320), nullable=False),
        sa.Column("proposal_type", sa.String(length=40), nullable=False, server_default="investigation_task"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False, server_default=""),
        sa.Column("capability_id", sa.String(length=100), nullable=True),
        sa.Column("profile_id", sa.String(length=100), nullable=True),
        sa.Column("priority", sa.String(length=30), nullable=False, server_default="medium"),
        sa.Column("risk_level", sa.String(length=30), nullable=False, server_default="low"),
        sa.Column("expected_gain", sa.Text(), nullable=False, server_default=""),
        sa.Column("action_intent", sa.Text(), nullable=False, server_default=""),
        sa.Column("action_params", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("context_refs", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("produced_by", sa.String(length=100), nullable=False, server_default="agent-task-runtime"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_id"], ["agent_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_message_id"], ["agent_task_messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("proposal_key", name="uq_agent_action_proposals_key"),
        sa.CheckConstraint("agent_key != ''", name="ck_agent_action_proposals_agent_not_empty"),
        sa.CheckConstraint("proposal_key != ''", name="ck_agent_action_proposals_key_not_empty"),
        sa.CheckConstraint(f"proposal_type IN {PROPOSAL_TYPES}", name="ck_agent_action_proposals_type_valid"),
        sa.CheckConstraint(f"status IN {PROPOSAL_STATUSES}", name="ck_agent_action_proposals_status_valid"),
        sa.CheckConstraint("title != ''", name="ck_agent_action_proposals_title_not_empty"),
        sa.CheckConstraint("summary != ''", name="ck_agent_action_proposals_summary_not_empty"),
        sa.CheckConstraint("priority != ''", name="ck_agent_action_proposals_priority_not_empty"),
        sa.CheckConstraint("risk_level != ''", name="ck_agent_action_proposals_risk_not_empty"),
        sa.CheckConstraint("produced_by != ''", name="ck_agent_action_proposals_producer_not_empty"),
    )
    op.create_index("ix_agent_action_proposals_program_id", "agent_action_proposals", ["program_id"])
    op.create_index("ix_agent_action_proposals_campaign_id", "agent_action_proposals", ["campaign_id"])
    op.create_index("ix_agent_action_proposals_task_id", "agent_action_proposals", ["task_id"])
    op.create_index("ix_agent_action_proposals_source_message_id", "agent_action_proposals", ["source_message_id"])
    op.create_index("ix_agent_action_proposals_agent_key", "agent_action_proposals", ["agent_key"])
    op.create_index("ix_agent_action_proposals_proposal_type", "agent_action_proposals", ["proposal_type"])
    op.create_index("ix_agent_action_proposals_status", "agent_action_proposals", ["status"])
    op.create_index("ix_agent_action_proposals_capability_id", "agent_action_proposals", ["capability_id"])
    op.create_index("ix_agent_action_proposals_profile_id", "agent_action_proposals", ["profile_id"])
    op.create_index(
        "idx_agent_action_proposals_program_status_created",
        "agent_action_proposals",
        ["program_id", "status", "created_at"],
    )
    op.create_index(
        "idx_agent_action_proposals_task_status_created",
        "agent_action_proposals",
        ["task_id", "status", "created_at"],
    )
    op.create_index(
        "idx_agent_action_proposals_capability_profile",
        "agent_action_proposals",
        ["capability_id", "profile_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_agent_action_proposals_capability_profile", table_name="agent_action_proposals")
    op.drop_index("idx_agent_action_proposals_task_status_created", table_name="agent_action_proposals")
    op.drop_index("idx_agent_action_proposals_program_status_created", table_name="agent_action_proposals")
    op.drop_index("ix_agent_action_proposals_profile_id", table_name="agent_action_proposals")
    op.drop_index("ix_agent_action_proposals_capability_id", table_name="agent_action_proposals")
    op.drop_index("ix_agent_action_proposals_status", table_name="agent_action_proposals")
    op.drop_index("ix_agent_action_proposals_proposal_type", table_name="agent_action_proposals")
    op.drop_index("ix_agent_action_proposals_agent_key", table_name="agent_action_proposals")
    op.drop_index("ix_agent_action_proposals_source_message_id", table_name="agent_action_proposals")
    op.drop_index("ix_agent_action_proposals_task_id", table_name="agent_action_proposals")
    op.drop_index("ix_agent_action_proposals_campaign_id", table_name="agent_action_proposals")
    op.drop_index("ix_agent_action_proposals_program_id", table_name="agent_action_proposals")
    op.drop_table("agent_action_proposals")
