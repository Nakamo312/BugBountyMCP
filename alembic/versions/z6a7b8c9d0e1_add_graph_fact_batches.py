"""Add durable GraphFactBatch store.

Revision ID: z6a7b8c9d0e1
Revises: y5z6a7b8c9d0
Create Date: 2026-06-13 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "z6a7b8c9d0e1"
down_revision = "y5z6a7b8c9d0"
branch_labels = None
depends_on = None


UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "graph_fact_batches",
        sa.Column("id", UUID, nullable=False),
        sa.Column("program_id", UUID, nullable=False),
        sa.Column("produced_by", sa.String(length=150), nullable=False),
        sa.Column("parser_version", sa.String(length=100), nullable=False),
        sa.Column("facts_json", JSONB, nullable=False),
        sa.Column("fact_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("locked_by", sa.String(length=100), nullable=True),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.CheckConstraint("produced_by != ''", name="ck_graph_fact_batches_produced_by_not_empty"),
        sa.CheckConstraint("parser_version != ''", name="ck_graph_fact_batches_parser_version_not_empty"),
        sa.CheckConstraint("fact_count > 0", name="ck_graph_fact_batches_fact_count_positive"),
        sa.CheckConstraint("attempts >= 0", name="ck_graph_fact_batches_attempts_nonnegative"),
        sa.CheckConstraint(
            "status IN ('pending', 'locked', 'applied', 'failed', 'dead')",
            name="ck_graph_fact_batches_status_valid",
        ),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_graph_fact_batches_program_id", "graph_fact_batches", ["program_id"])
    op.create_index("ix_graph_fact_batches_status", "graph_fact_batches", ["status"])
    op.create_index("ix_graph_fact_batches_available_at", "graph_fact_batches", ["available_at"])
    op.create_index(
        "idx_graph_fact_batches_status_available",
        "graph_fact_batches",
        ["status", "available_at"],
    )
    op.create_index(
        "idx_graph_fact_batches_program_created",
        "graph_fact_batches",
        ["program_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_graph_fact_batches_program_created", table_name="graph_fact_batches")
    op.drop_index("idx_graph_fact_batches_status_available", table_name="graph_fact_batches")
    op.drop_index("ix_graph_fact_batches_available_at", table_name="graph_fact_batches")
    op.drop_index("ix_graph_fact_batches_status", table_name="graph_fact_batches")
    op.drop_index("ix_graph_fact_batches_program_id", table_name="graph_fact_batches")
    op.drop_table("graph_fact_batches")
