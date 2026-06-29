"""Add durable projection watermarks and lag state.

Revision ID: c9d0e1f2g3h5
Revises: b8c9d0e1f2g4
Create Date: 2026-06-22 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "c9d0e1f2g3h5"
down_revision = "b8c9d0e1f2g4"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "projection_watermarks",
        sa.Column("id", UUID, nullable=False),
        sa.Column("program_id", UUID, nullable=False),
        sa.Column("projection_type", sa.String(length=50), nullable=False),
        sa.Column("projection_name", sa.String(length=150), nullable=False),
        sa.Column("source_watermark", sa.Text(), nullable=False),
        sa.Column("applied_watermark", sa.Text(), nullable=True),
        sa.Column("lag_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="observed"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("projection_type != ''", name="ck_projection_watermarks_type_not_empty"),
        sa.CheckConstraint("projection_name != ''", name="ck_projection_watermarks_name_not_empty"),
        sa.CheckConstraint("source_watermark != ''", name="ck_projection_watermarks_source_not_empty"),
        sa.CheckConstraint("lag_count >= 0", name="ck_projection_watermarks_lag_nonnegative"),
        sa.CheckConstraint(
            "status IN ('observed', 'running', 'ready', 'failed')",
            name="ck_projection_watermarks_status_valid",
        ),
        sa.CheckConstraint(
            "status != 'ready' OR (lag_count = 0 AND source_watermark = applied_watermark)",
            name="ck_projection_watermarks_ready_consistent",
        ),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "program_id",
            "projection_type",
            "projection_name",
            name="uq_projection_watermarks_program_projection",
        ),
    )
    op.create_index(
        "idx_projection_watermarks_program_status",
        "projection_watermarks",
        ["program_id", "status"],
    )
    op.execute(
        """
CREATE OR REPLACE FUNCTION mark_opensearch_projection_observed()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    source_row jsonb;
    source_program_id uuid;
    next_watermark text;
BEGIN
    source_row := COALESCE(to_jsonb(NEW), to_jsonb(OLD));
    source_program_id := (source_row ->> 'program_id')::uuid;
    next_watermark := txid_current()::text || ':' || clock_timestamp()::text;

    INSERT INTO projection_watermarks (
        id,
        program_id,
        projection_type,
        projection_name,
        source_watermark,
        lag_count,
        status,
        observed_at,
        updated_at
    ) VALUES (
        gen_random_uuid(),
        source_program_id,
        'opensearch',
        TG_ARGV[0],
        next_watermark,
        1,
        'observed',
        now(),
        now()
    )
    ON CONFLICT (program_id, projection_type, projection_name)
    DO UPDATE SET
        source_watermark = EXCLUDED.source_watermark,
        lag_count = projection_watermarks.lag_count + 1,
        status = 'observed',
        observed_at = EXCLUDED.observed_at,
        updated_at = EXCLUDED.updated_at,
        last_error = NULL;

    RETURN COALESCE(NEW, OLD);
END
$$;
        """
    )
    for table_name, projection_name in (
        ("http_observations", "http-observations"),
        ("raw_artifacts", "artifacts"),
        ("findings", "findings"),
        ("event_store", "detection-signals"),
    ):
        op.execute(
            f"""
CREATE TRIGGER {table_name}_opensearch_projection_observed
AFTER INSERT OR UPDATE OR DELETE ON {table_name}
FOR EACH ROW
EXECUTE FUNCTION mark_opensearch_projection_observed('{projection_name}');
            """
        )
        op.execute(
            f"""
INSERT INTO projection_watermarks (
    id, program_id, projection_type, projection_name,
    source_watermark, lag_count, status
)
SELECT
    gen_random_uuid(),
    program_id,
    'opensearch',
    '{projection_name}',
    'seed:' || count(*)::text,
    count(*)::integer,
    'observed'
FROM {table_name}
GROUP BY program_id
ON CONFLICT (program_id, projection_type, projection_name) DO NOTHING;
            """
        )


def downgrade() -> None:
    for table_name in (
        "event_store",
        "findings",
        "raw_artifacts",
        "http_observations",
    ):
        op.execute(
            f"DROP TRIGGER IF EXISTS {table_name}_opensearch_projection_observed ON {table_name};"
        )
    op.execute("DROP FUNCTION IF EXISTS mark_opensearch_projection_observed();")
    op.drop_index("idx_projection_watermarks_program_status", table_name="projection_watermarks")
    op.drop_table("projection_watermarks")
