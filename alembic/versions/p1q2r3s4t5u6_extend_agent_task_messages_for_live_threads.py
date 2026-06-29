"""Extend agent task messages for live agent threads.

Revision ID: p1q2r3s4t5u6
Revises: o0p1q2r3s4t5
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "p1q2r3s4t5u6"
down_revision = "o0p1q2r3s4t5"
branch_labels = None
depends_on = None

JSONB = postgresql.JSONB(astext_type=sa.Text())
MESSAGE_KINDS = "('note', 'finding', 'proposal', 'question', 'decision', 'error')"


def upgrade() -> None:
    op.add_column(
        "agent_task_messages",
        sa.Column("message_kind", sa.String(length=30), nullable=False, server_default="note"),
    )
    op.add_column(
        "agent_task_messages",
        sa.Column("action_refs", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.add_column(
        "agent_task_messages",
        sa.Column("proposal_refs", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.add_column(
        "agent_task_messages",
        sa.Column("decision_refs", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.add_column(
        "agent_task_messages",
        sa.Column("metadata", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_check_constraint(
        "ck_agent_task_messages_kind_valid",
        "agent_task_messages",
        f"message_kind IN {MESSAGE_KINDS}",
    )


def downgrade() -> None:
    op.drop_constraint("ck_agent_task_messages_kind_valid", "agent_task_messages", type_="check")
    op.drop_column("agent_task_messages", "metadata")
    op.drop_column("agent_task_messages", "decision_refs")
    op.drop_column("agent_task_messages", "proposal_refs")
    op.drop_column("agent_task_messages", "action_refs")
    op.drop_column("agent_task_messages", "message_kind")
