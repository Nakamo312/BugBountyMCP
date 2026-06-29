"""Add durable Surface Component analysis event queue.

Revision ID: c7d8e9f0a1b2
Revises: b7c8d9e0f1a2
Create Date: 2026-06-27 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c7d8e9f0a1b2"
down_revision: Union[str, None] = "b7c8d9e0f1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSONB = postgresql.JSONB(astext_type=sa.Text())
UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "surface_component_analysis_events",
        sa.Column("id", UUID, nullable=False),
        sa.Column("program_id", UUID, nullable=False),
        sa.Column("snapshot_id", UUID, nullable=False),
        sa.Column("previous_snapshot_id", UUID, nullable=True),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("analysis_version", sa.String(length=100), nullable=False),
        sa.Column("dedupe_key", sa.String(length=300), nullable=False),
        sa.Column("settings_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("result_json", JSONB, nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("locked_by", sa.String(length=100), nullable=True),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.CheckConstraint("event_type != ''", name="ck_surface_component_analysis_events_type_not_empty"),
        sa.CheckConstraint("analysis_version != ''", name="ck_surface_component_analysis_events_version_not_empty"),
        sa.CheckConstraint("dedupe_key != ''", name="ck_surface_component_analysis_events_dedupe_not_empty"),
        sa.CheckConstraint("attempts >= 0", name="ck_surface_component_analysis_events_attempts_nonnegative"),
        sa.CheckConstraint(
            "status IN ('pending', 'locked', 'processed', 'failed', 'dead')",
            name="ck_surface_component_analysis_events_status_valid",
        ),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["surface_snapshots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["previous_snapshot_id"], ["surface_snapshots.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_surface_component_analysis_events_program_id", "surface_component_analysis_events", ["program_id"])
    op.create_index("ix_surface_component_analysis_events_snapshot_id", "surface_component_analysis_events", ["snapshot_id"])
    op.create_index("ix_surface_component_analysis_events_status", "surface_component_analysis_events", ["status"])
    op.create_index("ix_surface_component_analysis_events_available_at", "surface_component_analysis_events", ["available_at"])
    op.create_index(
        "idx_surface_component_analysis_events_status_available",
        "surface_component_analysis_events",
        ["status", "available_at"],
    )
    op.create_index(
        "uq_surface_component_analysis_events_dedupe_key",
        "surface_component_analysis_events",
        ["dedupe_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_surface_component_analysis_events_dedupe_key", table_name="surface_component_analysis_events")
    op.drop_index("idx_surface_component_analysis_events_status_available", table_name="surface_component_analysis_events")
    op.drop_index("ix_surface_component_analysis_events_available_at", table_name="surface_component_analysis_events")
    op.drop_index("ix_surface_component_analysis_events_status", table_name="surface_component_analysis_events")
    op.drop_index("ix_surface_component_analysis_events_snapshot_id", table_name="surface_component_analysis_events")
    op.drop_index("ix_surface_component_analysis_events_program_id", table_name="surface_component_analysis_events")
    op.drop_table("surface_component_analysis_events")
