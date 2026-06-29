"""Add Cypher Gateway query audit table.

Revision ID: e1f2g3h4i5j6
Revises: d0e1f2g3h4i6
Create Date: 2026-06-23 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "e1f2g3h4i5j6"
down_revision = "d0e1f2g3h4i6"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "cypher_query_audits",
        sa.Column("id", UUID, nullable=False),
        sa.Column("program_id", UUID, nullable=False),
        sa.Column("workflow_id", UUID, nullable=True),
        sa.Column("actor", sa.String(length=100), nullable=False),
        sa.Column("query_hash", sa.String(length=64), nullable=False),
        sa.Column("params_hash", sa.String(length=64), nullable=False),
        sa.Column("allowed", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("timeout_seconds", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("actor != ''", name="ck_cypher_query_audits_actor_not_empty"),
        sa.CheckConstraint("query_hash != ''", name="ck_cypher_query_audits_query_hash_not_empty"),
        sa.CheckConstraint("params_hash != ''", name="ck_cypher_query_audits_params_hash_not_empty"),
        sa.CheckConstraint("row_count >= 0", name="ck_cypher_query_audits_row_count_nonnegative"),
        sa.CheckConstraint("timeout_seconds > 0", name="ck_cypher_query_audits_timeout_positive"),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_id"], ["agent_workflows.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_cypher_query_audits_program_created",
        "cypher_query_audits",
        ["program_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_cypher_query_audits_program_created", table_name="cypher_query_audits")
    op.drop_table("cypher_query_audits")
