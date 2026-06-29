"""Add durable agent coordination tables.

Revision ID: d0e1f2g3h4i6
Revises: c9d0e1f2g3h5
Create Date: 2026-06-23 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "d0e1f2g3h4i6"
down_revision = "c9d0e1f2g3h5"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "agent_workflows",
        sa.Column("id", UUID, nullable=False),
        sa.Column("program_id", UUID, nullable=False),
        sa.Column("campaign_id", UUID, nullable=True),
        sa.Column("correlation_id", UUID, nullable=False),
        sa.Column("workflow_type", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="created"),
        sa.Column("metadata", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("workflow_type != ''", name="ck_agent_workflows_type_not_empty"),
        sa.CheckConstraint(
            "status IN ('created', 'running', 'waiting', 'completed', 'failed', 'cancelled')",
            name="ck_agent_workflows_status_valid",
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_agent_workflows_program_status", "agent_workflows", ["program_id", "status"])
    op.create_index("idx_agent_workflows_scope", "agent_workflows", ["program_id", "campaign_id", "correlation_id"])

    op.create_table(
        "agent_workflow_runs",
        sa.Column("id", UUID, nullable=False),
        sa.Column("workflow_id", UUID, nullable=False),
        sa.Column("program_id", UUID, nullable=False),
        sa.Column("campaign_id", UUID, nullable=True),
        sa.Column("correlation_id", UUID, nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="queued"),
        sa.Column("current_node", sa.String(length=150), nullable=True),
        sa.Column("checkpoint_ref", sa.Text(), nullable=True),
        sa.Column("metadata", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'waiting', 'completed', 'failed', 'cancelled')",
            name="ck_agent_workflow_runs_status_valid",
        ),
        sa.CheckConstraint(
            "current_node IS NULL OR current_node != ''",
            name="ck_agent_workflow_runs_current_node_not_empty",
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_id"], ["agent_workflows.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_agent_workflow_runs_workflow_status", "agent_workflow_runs", ["workflow_id", "status"])
    op.create_index(
        "idx_agent_workflow_runs_scope",
        "agent_workflow_runs",
        ["program_id", "campaign_id", "correlation_id"],
    )

    op.create_table(
        "agent_subscriptions",
        sa.Column("id", UUID, nullable=False),
        sa.Column("workflow_id", UUID, nullable=True),
        sa.Column("workflow_run_id", UUID, nullable=True),
        sa.Column("program_id", UUID, nullable=False),
        sa.Column("campaign_id", UUID, nullable=True),
        sa.Column("correlation_id", UUID, nullable=True),
        sa.Column("event_type", sa.String(length=150), nullable=False),
        sa.Column("inbox_key", sa.String(length=200), nullable=False),
        sa.Column("dedupe_key", sa.String(length=300), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="active"),
        sa.Column("metadata", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("event_type != ''", name="ck_agent_subscriptions_event_type_not_empty"),
        sa.CheckConstraint("inbox_key != ''", name="ck_agent_subscriptions_inbox_key_not_empty"),
        sa.CheckConstraint("dedupe_key != ''", name="ck_agent_subscriptions_dedupe_key_not_empty"),
        sa.CheckConstraint(
            "status IN ('active', 'paused', 'cancelled')",
            name="ck_agent_subscriptions_status_valid",
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_id"], ["agent_workflows.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_run_id"], ["agent_workflow_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key", name="uq_agent_subscriptions_dedupe_key"),
    )
    op.create_index(
        "idx_agent_subscriptions_scope_event_status",
        "agent_subscriptions",
        ["program_id", "campaign_id", "correlation_id", "event_type", "status"],
    )

    op.create_table(
        "agent_inbox",
        sa.Column("id", UUID, nullable=False),
        sa.Column("subscription_id", UUID, nullable=True),
        sa.Column("workflow_id", UUID, nullable=True),
        sa.Column("workflow_run_id", UUID, nullable=True),
        sa.Column("program_id", UUID, nullable=False),
        sa.Column("campaign_id", UUID, nullable=True),
        sa.Column("correlation_id", UUID, nullable=True),
        sa.Column("event_id", UUID, nullable=True),
        sa.Column("message_type", sa.String(length=150), nullable=False),
        sa.Column("payload", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("dedupe_key", sa.String(length=300), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("locked_by", sa.String(length=100), nullable=True),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.CheckConstraint("message_type != ''", name="ck_agent_inbox_message_type_not_empty"),
        sa.CheckConstraint("dedupe_key != ''", name="ck_agent_inbox_dedupe_key_not_empty"),
        sa.CheckConstraint("attempts >= 0", name="ck_agent_inbox_attempts_nonnegative"),
        sa.CheckConstraint(
            "status IN ('pending', 'claimed', 'processed', 'failed', 'dead', 'cancelled')",
            name="ck_agent_inbox_status_valid",
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["event_id"], ["event_store.event_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subscription_id"], ["agent_subscriptions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workflow_id"], ["agent_workflows.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_run_id"], ["agent_workflow_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key", name="uq_agent_inbox_dedupe_key"),
    )
    op.create_index("idx_agent_inbox_status_available", "agent_inbox", ["status", "available_at"])
    op.create_index(
        "idx_agent_inbox_scope_status",
        "agent_inbox",
        ["program_id", "campaign_id", "correlation_id", "status"],
    )

    op.create_table(
        "agent_wait_conditions",
        sa.Column("id", UUID, nullable=False),
        sa.Column("workflow_run_id", UUID, nullable=False),
        sa.Column("program_id", UUID, nullable=False),
        sa.Column("campaign_id", UUID, nullable=True),
        sa.Column("correlation_id", UUID, nullable=True),
        sa.Column("condition_type", sa.String(length=50), nullable=False),
        sa.Column("condition_key", sa.String(length=300), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("required_state", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("resolved_payload", JSONB, nullable=True),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("condition_key != ''", name="ck_agent_wait_conditions_key_not_empty"),
        sa.CheckConstraint(
            "condition_type IN ('tool_run_completed', 'ingestion_completed', 'projections_ready', 'new_facts_available', 'campaign_quiescent')",
            name="ck_agent_wait_conditions_type_valid",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'resolved', 'timed_out', 'cancelled')",
            name="ck_agent_wait_conditions_status_valid",
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_run_id"], ["agent_workflow_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workflow_run_id", "condition_key", name="uq_agent_wait_conditions_run_key"),
    )
    op.create_index(
        "idx_agent_wait_conditions_status_deadline",
        "agent_wait_conditions",
        ["status", "deadline_at"],
    )
    op.create_index(
        "idx_agent_wait_conditions_scope_type",
        "agent_wait_conditions",
        ["program_id", "campaign_id", "correlation_id", "condition_type"],
    )

    op.create_table(
        "agent_result_sets",
        sa.Column("id", UUID, nullable=False),
        sa.Column("workflow_id", UUID, nullable=True),
        sa.Column("workflow_run_id", UUID, nullable=True),
        sa.Column("action_id", UUID, nullable=True),
        sa.Column("program_id", UUID, nullable=False),
        sa.Column("campaign_id", UUID, nullable=True),
        sa.Column("correlation_id", UUID, nullable=True),
        sa.Column("result_type", sa.String(length=100), nullable=False),
        sa.Column("result_key", sa.String(length=300), nullable=False),
        sa.Column("payload", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("artifact_refs", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("fact_refs", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("search_refs", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("graph_refs", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("result_type != ''", name="ck_agent_result_sets_type_not_empty"),
        sa.CheckConstraint("result_key != ''", name="ck_agent_result_sets_key_not_empty"),
        sa.ForeignKeyConstraint(["action_id"], ["action_requests.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_id"], ["agent_workflows.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_run_id"], ["agent_workflow_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("program_id", "result_key", name="uq_agent_result_sets_program_key"),
    )
    op.create_index(
        "idx_agent_result_sets_scope_type",
        "agent_result_sets",
        ["program_id", "campaign_id", "correlation_id", "result_type"],
    )


def downgrade() -> None:
    op.drop_index("idx_agent_result_sets_scope_type", table_name="agent_result_sets")
    op.drop_table("agent_result_sets")

    op.drop_index("idx_agent_wait_conditions_scope_type", table_name="agent_wait_conditions")
    op.drop_index("idx_agent_wait_conditions_status_deadline", table_name="agent_wait_conditions")
    op.drop_table("agent_wait_conditions")

    op.drop_index("idx_agent_inbox_scope_status", table_name="agent_inbox")
    op.drop_index("idx_agent_inbox_status_available", table_name="agent_inbox")
    op.drop_table("agent_inbox")

    op.drop_index("idx_agent_subscriptions_scope_event_status", table_name="agent_subscriptions")
    op.drop_table("agent_subscriptions")

    op.drop_index("idx_agent_workflow_runs_scope", table_name="agent_workflow_runs")
    op.drop_index("idx_agent_workflow_runs_workflow_status", table_name="agent_workflow_runs")
    op.drop_table("agent_workflow_runs")

    op.drop_index("idx_agent_workflows_scope", table_name="agent_workflows")
    op.drop_index("idx_agent_workflows_program_status", table_name="agent_workflows")
    op.drop_table("agent_workflows")
