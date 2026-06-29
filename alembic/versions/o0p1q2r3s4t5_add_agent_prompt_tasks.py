"""Add user-facing agent prompt tasks.

Revision ID: o0p1q2r3s4t5
Revises: n9o0p1q2r3s4
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "o0p1q2r3s4t5"
down_revision = "n9o0p1q2r3s4"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())

TASK_STATUSES = "('queued', 'claimed', 'waiting', 'completed', 'failed', 'cancelled')"
MESSAGE_ROLES = "('user', 'agent', 'system')"


def upgrade() -> None:
    op.create_table(
        "agent_tasks",
        sa.Column("id", UUID, nullable=False),
        sa.Column("program_id", UUID, nullable=False),
        sa.Column("campaign_id", UUID, nullable=True),
        sa.Column("correlation_id", UUID, nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="queued"),
        sa.Column("target_agent", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("prompt_excerpt", sa.Text(), nullable=False),
        sa.Column("prompt_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.String(length=150), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False, server_default="ui"),
        sa.Column("context_refs", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("metadata", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("inbox_message_id", UUID, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["inbox_message_id"], ["agent_inbox.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(f"status IN {TASK_STATUSES}", name="ck_agent_tasks_status_valid"),
        sa.CheckConstraint("target_agent != ''", name="ck_agent_tasks_target_agent_not_empty"),
        sa.CheckConstraint("title != ''", name="ck_agent_tasks_title_not_empty"),
        sa.CheckConstraint("prompt_excerpt != ''", name="ck_agent_tasks_prompt_not_empty"),
        sa.CheckConstraint("prompt_hash != ''", name="ck_agent_tasks_prompt_hash_not_empty"),
        sa.CheckConstraint("created_by != ''", name="ck_agent_tasks_created_by_not_empty"),
        sa.CheckConstraint("source != ''", name="ck_agent_tasks_source_not_empty"),
    )
    op.create_index("ix_agent_tasks_program_id", "agent_tasks", ["program_id"])
    op.create_index("ix_agent_tasks_campaign_id", "agent_tasks", ["campaign_id"])
    op.create_index("ix_agent_tasks_correlation_id", "agent_tasks", ["correlation_id"])
    op.create_index("ix_agent_tasks_status", "agent_tasks", ["status"])
    op.create_index("ix_agent_tasks_target_agent", "agent_tasks", ["target_agent"])
    op.create_index("ix_agent_tasks_inbox_message_id", "agent_tasks", ["inbox_message_id"])
    op.create_index("idx_agent_tasks_program_status_created", "agent_tasks", ["program_id", "status", "created_at"])
    op.create_index("idx_agent_tasks_campaign_status_created", "agent_tasks", ["campaign_id", "status", "created_at"])
    op.create_index("idx_agent_tasks_prompt_hash", "agent_tasks", ["program_id", "prompt_hash"])

    op.create_table(
        "agent_task_messages",
        sa.Column("id", UUID, nullable=False),
        sa.Column("task_id", UUID, nullable=False),
        sa.Column("program_id", UUID, nullable=False),
        sa.Column("campaign_id", UUID, nullable=True),
        sa.Column("correlation_id", UUID, nullable=False),
        sa.Column("role", sa.String(length=30), nullable=False),
        sa.Column("agent_key", sa.String(length=100), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("body_hash", sa.String(length=64), nullable=False),
        sa.Column("artifact_refs", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("fact_refs", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("graph_refs", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["task_id"], ["agent_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(f"role IN {MESSAGE_ROLES}", name="ck_agent_task_messages_role_valid"),
        sa.CheckConstraint("body != ''", name="ck_agent_task_messages_body_not_empty"),
        sa.CheckConstraint("body_hash != ''", name="ck_agent_task_messages_body_hash_not_empty"),
    )
    op.create_index("ix_agent_task_messages_task_id", "agent_task_messages", ["task_id"])
    op.create_index("ix_agent_task_messages_program_id", "agent_task_messages", ["program_id"])
    op.create_index("ix_agent_task_messages_campaign_id", "agent_task_messages", ["campaign_id"])
    op.create_index("ix_agent_task_messages_correlation_id", "agent_task_messages", ["correlation_id"])
    op.create_index("ix_agent_task_messages_agent_key", "agent_task_messages", ["agent_key"])
    op.create_index("idx_agent_task_messages_task_created", "agent_task_messages", ["task_id", "created_at"])
    op.create_index(
        "idx_agent_task_messages_scope_created",
        "agent_task_messages",
        ["program_id", "campaign_id", "correlation_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_agent_task_messages_scope_created", table_name="agent_task_messages")
    op.drop_index("idx_agent_task_messages_task_created", table_name="agent_task_messages")
    op.drop_index("ix_agent_task_messages_agent_key", table_name="agent_task_messages")
    op.drop_index("ix_agent_task_messages_correlation_id", table_name="agent_task_messages")
    op.drop_index("ix_agent_task_messages_campaign_id", table_name="agent_task_messages")
    op.drop_index("ix_agent_task_messages_program_id", table_name="agent_task_messages")
    op.drop_index("ix_agent_task_messages_task_id", table_name="agent_task_messages")
    op.drop_table("agent_task_messages")
    op.drop_index("idx_agent_tasks_prompt_hash", table_name="agent_tasks")
    op.drop_index("idx_agent_tasks_campaign_status_created", table_name="agent_tasks")
    op.drop_index("idx_agent_tasks_program_status_created", table_name="agent_tasks")
    op.drop_index("ix_agent_tasks_inbox_message_id", table_name="agent_tasks")
    op.drop_index("ix_agent_tasks_target_agent", table_name="agent_tasks")
    op.drop_index("ix_agent_tasks_status", table_name="agent_tasks")
    op.drop_index("ix_agent_tasks_correlation_id", table_name="agent_tasks")
    op.drop_index("ix_agent_tasks_campaign_id", table_name="agent_tasks")
    op.drop_index("ix_agent_tasks_program_id", table_name="agent_tasks")
    op.drop_table("agent_tasks")
