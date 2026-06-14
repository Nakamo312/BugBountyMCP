"""Add action request schema v2 fields.

Revision ID: w3x4y5z6a7b8
Revises: v2w3x4y5z6a7
Create Date: 2026-06-11 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "w3x4y5z6a7b8"
down_revision: Union[str, None] = "v2w3x4y5z6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


JSONB = postgresql.JSONB(astext_type=sa.Text())
UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "campaigns",
        sa.Column("id", UUID, nullable=False),
        sa.Column("program_id", UUID, nullable=False),
        sa.Column("correlation_id", UUID, nullable=False),
        sa.Column("workflow_id", UUID, nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("metadata", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('created', 'running', 'expanding', 'waiting_for_projections', 'quiescent', 'closed', 'cancelled', 'failed')",
            name="ck_campaigns_status_valid",
        ),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_campaigns_program_id", "campaigns", ["program_id"])
    op.create_index("ix_campaigns_correlation_id", "campaigns", ["correlation_id"])
    op.create_index("ix_campaigns_workflow_id", "campaigns", ["workflow_id"])
    op.create_index("ix_campaigns_status", "campaigns", ["status"])
    op.create_index("idx_campaigns_program_status", "campaigns", ["program_id", "status"])

    op.add_column("action_requests", sa.Column("workflow_id", UUID, nullable=True))
    op.add_column("action_requests", sa.Column("campaign_id", UUID, nullable=True))
    op.add_column("action_requests", sa.Column("correlation_id", UUID, nullable=True))
    op.add_column("action_requests", sa.Column("catalog_hash", sa.String(length=64), nullable=True))
    op.add_column("action_requests", sa.Column("metadata", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.create_index("ix_action_requests_workflow_id", "action_requests", ["workflow_id"])
    op.create_index("ix_action_requests_campaign_id", "action_requests", ["campaign_id"])
    op.create_index("ix_action_requests_correlation_id", "action_requests", ["correlation_id"])
    op.create_index("ix_action_requests_catalog_hash", "action_requests", ["catalog_hash"])
    op.create_index("idx_action_requests_campaign_status", "action_requests", ["campaign_id", "status"])
    op.create_foreign_key(
        "fk_action_requests_campaign_id_campaigns",
        "action_requests",
        "campaigns",
        ["campaign_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "action_request_targets",
        sa.Column("id", UUID, nullable=False),
        sa.Column("action_id", UUID, nullable=False),
        sa.Column("target", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("target != ''", name="ck_action_request_targets_not_empty"),
        sa.CheckConstraint("position >= 0", name="ck_action_request_targets_position_nonnegative"),
        sa.CheckConstraint("status IN ('requested', 'allowed', 'blocked')", name="ck_action_request_targets_status_valid"),
        sa.ForeignKeyConstraint(["action_id"], ["action_requests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("action_id", "position", name="uq_action_request_targets_action_position"),
    )
    op.create_index("ix_action_request_targets_action_id", "action_request_targets", ["action_id"])
    op.create_index("ix_action_request_targets_status", "action_request_targets", ["status"])
    op.create_index("idx_action_request_targets_action_status", "action_request_targets", ["action_id", "status"])

    op.create_table(
        "action_request_options",
        sa.Column("id", UUID, nullable=False),
        sa.Column("action_id", UUID, nullable=False),
        sa.Column("option_key", sa.String(length=200), nullable=False),
        sa.Column("option_value", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("option_key != ''", name="ck_action_request_options_key_not_empty"),
        sa.ForeignKeyConstraint(["action_id"], ["action_requests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("action_id", "option_key", name="uq_action_request_options_action_key"),
    )
    op.create_index("ix_action_request_options_action_id", "action_request_options", ["action_id"])

    op.create_table(
        "scope_decisions",
        sa.Column("id", UUID, nullable=False),
        sa.Column("action_id", UUID, nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("scope_policy", sa.String(length=50), nullable=True),
        sa.Column("reasons", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("allowed_targets", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("blocked_targets", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("metadata", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('allowed', 'blocked', 'partial', 'not_evaluated')", name="ck_scope_decisions_status_valid"),
        sa.ForeignKeyConstraint(["action_id"], ["action_requests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scope_decisions_action_id", "scope_decisions", ["action_id"])
    op.create_index("ix_scope_decisions_status", "scope_decisions", ["status"])
    op.create_index("idx_scope_decisions_action_status", "scope_decisions", ["action_id", "status"])

    op.add_column("policy_decisions", sa.Column("safety_level", sa.String(length=30), nullable=True))
    op.add_column("policy_decisions", sa.Column("metadata", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.add_column("policy_decisions", sa.Column("catalog_hash", sa.String(length=64), nullable=True))
    op.create_index("ix_policy_decisions_safety_level", "policy_decisions", ["safety_level"])
    op.create_index("ix_policy_decisions_catalog_hash", "policy_decisions", ["catalog_hash"])

    op.create_table(
        "approval_requests",
        sa.Column("id", UUID, nullable=False),
        sa.Column("action_id", UUID, nullable=False),
        sa.Column("policy_decision_id", UUID, nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("requested_by", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('pending', 'approved', 'rejected', 'cancelled')", name="ck_approval_requests_status_valid"),
        sa.ForeignKeyConstraint(["action_id"], ["action_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["policy_decision_id"], ["policy_decisions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_approval_requests_action_id", "approval_requests", ["action_id"])
    op.create_index("ix_approval_requests_policy_decision_id", "approval_requests", ["policy_decision_id"])
    op.create_index("ix_approval_requests_status", "approval_requests", ["status"])
    op.create_index("idx_approval_requests_action_status", "approval_requests", ["action_id", "status"])

    op.create_table(
        "approval_decisions",
        sa.Column("id", UUID, nullable=False),
        sa.Column("approval_request_id", UUID, nullable=False),
        sa.Column("action_id", UUID, nullable=False),
        sa.Column("decision", sa.String(length=30), nullable=False),
        sa.Column("decided_by", sa.String(length=100), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("metadata", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("decision IN ('approved', 'rejected')", name="ck_approval_decisions_valid"),
        sa.ForeignKeyConstraint(["approval_request_id"], ["approval_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["action_id"], ["action_requests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_approval_decisions_approval_request_id", "approval_decisions", ["approval_request_id"])
    op.create_index("ix_approval_decisions_action_id", "approval_decisions", ["action_id"])
    op.create_index("ix_approval_decisions_decision", "approval_decisions", ["decision"])

    op.add_column("jobs", sa.Column("campaign_id", UUID, nullable=True))
    op.create_index("ix_jobs_campaign_id", "jobs", ["campaign_id"])
    op.create_foreign_key(
        "fk_jobs_campaign_id_campaigns",
        "jobs",
        "campaigns",
        ["campaign_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_jobs_campaign_id_campaigns", "jobs", type_="foreignkey")
    op.drop_index("ix_jobs_campaign_id", table_name="jobs")
    op.drop_column("jobs", "campaign_id")

    op.drop_index("ix_approval_decisions_decision", table_name="approval_decisions")
    op.drop_index("ix_approval_decisions_action_id", table_name="approval_decisions")
    op.drop_index("ix_approval_decisions_approval_request_id", table_name="approval_decisions")
    op.drop_table("approval_decisions")

    op.drop_index("idx_approval_requests_action_status", table_name="approval_requests")
    op.drop_index("ix_approval_requests_status", table_name="approval_requests")
    op.drop_index("ix_approval_requests_policy_decision_id", table_name="approval_requests")
    op.drop_index("ix_approval_requests_action_id", table_name="approval_requests")
    op.drop_table("approval_requests")

    op.drop_index("ix_policy_decisions_catalog_hash", table_name="policy_decisions")
    op.drop_index("ix_policy_decisions_safety_level", table_name="policy_decisions")
    op.drop_column("policy_decisions", "catalog_hash")
    op.drop_column("policy_decisions", "metadata")
    op.drop_column("policy_decisions", "safety_level")

    op.drop_index("idx_scope_decisions_action_status", table_name="scope_decisions")
    op.drop_index("ix_scope_decisions_status", table_name="scope_decisions")
    op.drop_index("ix_scope_decisions_action_id", table_name="scope_decisions")
    op.drop_table("scope_decisions")

    op.drop_index("ix_action_request_options_action_id", table_name="action_request_options")
    op.drop_table("action_request_options")

    op.drop_index("idx_action_request_targets_action_status", table_name="action_request_targets")
    op.drop_index("ix_action_request_targets_status", table_name="action_request_targets")
    op.drop_index("ix_action_request_targets_action_id", table_name="action_request_targets")
    op.drop_table("action_request_targets")

    op.drop_constraint("fk_action_requests_campaign_id_campaigns", "action_requests", type_="foreignkey")
    op.drop_index("idx_action_requests_campaign_status", table_name="action_requests")
    op.drop_index("ix_action_requests_catalog_hash", table_name="action_requests")
    op.drop_index("ix_action_requests_correlation_id", table_name="action_requests")
    op.drop_index("ix_action_requests_campaign_id", table_name="action_requests")
    op.drop_index("ix_action_requests_workflow_id", table_name="action_requests")
    op.drop_column("action_requests", "metadata")
    op.drop_column("action_requests", "catalog_hash")
    op.drop_column("action_requests", "correlation_id")
    op.drop_column("action_requests", "campaign_id")
    op.drop_column("action_requests", "workflow_id")

    op.drop_index("idx_campaigns_program_status", table_name="campaigns")
    op.drop_index("ix_campaigns_status", table_name="campaigns")
    op.drop_index("ix_campaigns_workflow_id", table_name="campaigns")
    op.drop_index("ix_campaigns_correlation_id", table_name="campaigns")
    op.drop_index("ix_campaigns_program_id", table_name="campaigns")
    op.drop_table("campaigns")
