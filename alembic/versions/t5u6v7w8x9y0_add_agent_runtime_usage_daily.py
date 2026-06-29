"""add agent runtime usage daily aggregates

Revision ID: t5u6v7w8x9y0
Revises: s4t5u6v7w8x9
Create Date: 2026-06-26 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "t5u6v7w8x9y0"
down_revision = "s4t5u6v7w8x9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_runtime_usage_daily",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("scope_key", sa.String(length=320), nullable=False),
        sa.Column("program_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("programs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True),
        sa.Column("usage_date", sa.Date(), nullable=False),
        sa.Column("total_agent_messages", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("runtime_decision_messages", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("requested_none_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("requested_cheap_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("requested_normal_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("requested_deep_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("selected_none_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("selected_cheap_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("selected_normal_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("selected_deep_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("llm_allowed_messages", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("no_model_messages", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("downgraded_messages", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deep_requested_messages", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deep_approved_messages", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deep_downgraded_messages", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("context_truncated_messages", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latest_message_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_task_messages.id", ondelete="SET NULL"), nullable=True),
        sa.Column("latest_selected_mode", sa.String(length=30), nullable=True),
        sa.Column("latest_requested_mode", sa.String(length=30), nullable=True),
        sa.Column("latest_reason_code", sa.String(length=120), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("scope_key", name="uq_agent_runtime_usage_daily_scope_key"),
        sa.CheckConstraint("scope_key != ''", name="ck_agent_runtime_usage_daily_scope_key_not_empty"),
        sa.CheckConstraint("total_agent_messages >= 0", name="ck_agent_runtime_usage_daily_total_nonnegative"),
        sa.CheckConstraint("runtime_decision_messages >= 0", name="ck_agent_runtime_usage_daily_decisions_nonnegative"),
        sa.CheckConstraint("latest_selected_mode IS NULL OR latest_selected_mode IN ('none', 'cheap', 'normal', 'deep')", name="ck_agent_runtime_usage_daily_latest_selected_valid"),
        sa.CheckConstraint("latest_requested_mode IS NULL OR latest_requested_mode IN ('none', 'cheap', 'normal', 'deep')", name="ck_agent_runtime_usage_daily_latest_requested_valid"),
    )
    op.create_index("idx_agent_runtime_usage_daily_program_date", "agent_runtime_usage_daily", ["program_id", "usage_date"])
    op.create_index("idx_agent_runtime_usage_daily_campaign_date", "agent_runtime_usage_daily", ["campaign_id", "usage_date"])


def downgrade() -> None:
    op.drop_index("idx_agent_runtime_usage_daily_campaign_date", table_name="agent_runtime_usage_daily")
    op.drop_index("idx_agent_runtime_usage_daily_program_date", table_name="agent_runtime_usage_daily")
    op.drop_table("agent_runtime_usage_daily")
