"""Add graph projection event queue for graph projector wakeups.

Revision ID: b8c9d0e1f2g3
Revises: a7b8c9d0e1f2
Create Date: 2026-06-13 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "b8c9d0e1f2g3"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "graph_projection_events",
        sa.Column("id", UUID, nullable=False),
        sa.Column("program_id", UUID, nullable=False),
        sa.Column("source_type", sa.String(length=100), nullable=False),
        sa.Column("source_id", UUID, nullable=False),
        sa.Column("event_type", sa.String(length=150), nullable=False),
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
        sa.CheckConstraint("source_type != ''", name="ck_graph_projection_events_source_type_not_empty"),
        sa.CheckConstraint("event_type != ''", name="ck_graph_projection_events_event_type_not_empty"),
        sa.CheckConstraint("dedupe_key != ''", name="ck_graph_projection_events_dedupe_key_not_empty"),
        sa.CheckConstraint("attempts >= 0", name="ck_graph_projection_events_attempts_nonnegative"),
        sa.CheckConstraint(
            "status IN ('pending', 'locked', 'processed', 'failed', 'dead')",
            name="ck_graph_projection_events_status_valid",
        ),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_graph_projection_events_program_id", "graph_projection_events", ["program_id"])
    op.create_index("ix_graph_projection_events_source_id", "graph_projection_events", ["source_id"])
    op.create_index("ix_graph_projection_events_status", "graph_projection_events", ["status"])
    op.create_index("ix_graph_projection_events_available_at", "graph_projection_events", ["available_at"])
    op.create_index(
        "idx_graph_projection_events_status_available",
        "graph_projection_events",
        ["status", "available_at"],
    )
    op.create_index(
        "idx_graph_projection_events_source",
        "graph_projection_events",
        ["source_type", "source_id"],
    )
    op.create_index(
        "uq_graph_projection_events_dedupe_key",
        "graph_projection_events",
        ["dedupe_key"],
        unique=True,
    )

    op.execute(
        """
CREATE OR REPLACE FUNCTION enqueue_raw_artifact_graph_projection_event()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    projection_dedupe_key text;
BEGIN
    IF NEW.run_id IS NULL THEN
        RETURN NEW;
    END IF;

    projection_dedupe_key := 'raw-artifact-created:' || NEW.id::text;

    INSERT INTO graph_projection_events (
        id,
        program_id,
        source_type,
        source_id,
        event_type,
        dedupe_key
    )
    VALUES (
        NEW.id,
        NEW.program_id,
        'raw_artifact',
        NEW.id,
        'raw_artifact_created',
        projection_dedupe_key
    )
    ON CONFLICT (dedupe_key) DO NOTHING;

    PERFORM pg_notify('graph_projection_events_changed', projection_dedupe_key);
    RETURN NEW;
END
$$;
        """
    )
    op.execute(
        """
CREATE TRIGGER raw_artifacts_graph_projection_event
AFTER INSERT ON raw_artifacts
FOR EACH ROW
EXECUTE FUNCTION enqueue_raw_artifact_graph_projection_event();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS raw_artifacts_graph_projection_event ON raw_artifacts;")
    op.execute("DROP FUNCTION IF EXISTS enqueue_raw_artifact_graph_projection_event();")
    op.drop_index("uq_graph_projection_events_dedupe_key", table_name="graph_projection_events")
    op.drop_index("idx_graph_projection_events_source", table_name="graph_projection_events")
    op.drop_index("idx_graph_projection_events_status_available", table_name="graph_projection_events")
    op.drop_index("ix_graph_projection_events_available_at", table_name="graph_projection_events")
    op.drop_index("ix_graph_projection_events_status", table_name="graph_projection_events")
    op.drop_index("ix_graph_projection_events_source_id", table_name="graph_projection_events")
    op.drop_index("ix_graph_projection_events_program_id", table_name="graph_projection_events")
    op.drop_table("graph_projection_events")
