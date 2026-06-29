"""Persist surface component analysis read model.

Revision ID: b7c8d9e0f1a2
Revises: t5u6v7w8x9y0
Create Date: 2026-06-27 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, None] = "t5u6v7w8x9y0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


JSONB = postgresql.JSONB(astext_type=sa.Text())
UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "surface_component_analysis_runs",
        sa.Column("id", UUID, nullable=False),
        sa.Column("program_id", UUID, nullable=False),
        sa.Column("snapshot_id", UUID, nullable=False),
        sa.Column("previous_snapshot_id", UUID, nullable=True),
        sa.Column("algorithm", sa.String(length=100), nullable=False),
        sa.Column("algorithm_version", sa.String(length=100), nullable=False),
        sa.Column("report_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("settings_json", JSONB, nullable=False),
        sa.Column("stats_json", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("algorithm != ''", name="ck_surface_component_analysis_runs_algorithm_not_empty"),
        sa.CheckConstraint("algorithm_version != ''", name="ck_surface_component_analysis_runs_algorithm_version_not_empty"),
        sa.CheckConstraint("report_fingerprint != ''", name="ck_surface_component_analysis_runs_fingerprint_not_empty"),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["surface_snapshots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["previous_snapshot_id"], ["surface_snapshots.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("program_id", "report_fingerprint", name="uq_surface_component_analysis_runs_program_fingerprint"),
    )
    op.create_index("ix_surface_component_analysis_runs_program_id", "surface_component_analysis_runs", ["program_id"])
    op.create_index("ix_surface_component_analysis_runs_snapshot_id", "surface_component_analysis_runs", ["snapshot_id"])
    op.create_index("idx_surface_component_analysis_runs_program_snapshot", "surface_component_analysis_runs", ["program_id", "snapshot_id", "created_at"])

    op.create_table(
        "surface_component_analysis_items",
        sa.Column("id", UUID, nullable=False),
        sa.Column("analysis_run_id", UUID, nullable=False),
        sa.Column("program_id", UUID, nullable=False),
        sa.Column("snapshot_id", UUID, nullable=False),
        sa.Column("component_id", sa.Integer(), nullable=False),
        sa.Column("node_count", sa.Integer(), nullable=False),
        sa.Column("changed_node_count", sa.Integer(), nullable=False),
        sa.Column("structural_pressure_score", sa.Integer(), nullable=True),
        sa.Column("drift_score", sa.Integer(), nullable=True),
        sa.Column("bridge_pressure_score", sa.Integer(), nullable=True),
        sa.Column("outlier_score", sa.Integer(), nullable=True),
        sa.Column("coverage_score", sa.Integer(), nullable=True),
        sa.Column("exploration_priority_score", sa.Integer(), nullable=True),
        sa.Column("action_candidate_count", sa.Integer(), nullable=False),
        sa.Column("metrics_json", JSONB, nullable=False),
        sa.Column("action_candidates_json", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("component_id >= 0", name="ck_surface_component_analysis_items_component_non_negative"),
        sa.CheckConstraint("node_count >= 0", name="ck_surface_component_analysis_items_node_count_non_negative"),
        sa.CheckConstraint("changed_node_count >= 0", name="ck_surface_component_analysis_items_changed_count_non_negative"),
        sa.CheckConstraint("action_candidate_count >= 0", name="ck_surface_component_analysis_items_candidate_count_nonneg"),
        sa.CheckConstraint("structural_pressure_score IS NULL OR (structural_pressure_score >= 0 AND structural_pressure_score <= 100)", name="ck_surface_component_analysis_items_structural_score_range"),
        sa.CheckConstraint("drift_score IS NULL OR (drift_score >= 0 AND drift_score <= 100)", name="ck_surface_component_analysis_items_drift_score_range"),
        sa.CheckConstraint("bridge_pressure_score IS NULL OR (bridge_pressure_score >= 0 AND bridge_pressure_score <= 100)", name="ck_surface_component_analysis_items_bridge_score_range"),
        sa.CheckConstraint("outlier_score IS NULL OR (outlier_score >= 0 AND outlier_score <= 100)", name="ck_surface_component_analysis_items_outlier_score_range"),
        sa.CheckConstraint("coverage_score IS NULL OR (coverage_score >= 0 AND coverage_score <= 100)", name="ck_surface_component_analysis_items_coverage_score_range"),
        sa.CheckConstraint("exploration_priority_score IS NULL OR (exploration_priority_score >= 0 AND exploration_priority_score <= 100)", name="ck_surface_component_analysis_items_exploration_score_range"),
        sa.ForeignKeyConstraint(["analysis_run_id"], ["surface_component_analysis_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["surface_snapshots.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("analysis_run_id", "component_id", name="uq_surface_component_analysis_items_run_component"),
    )
    op.create_index("ix_surface_component_analysis_items_analysis_run_id", "surface_component_analysis_items", ["analysis_run_id"])
    op.create_index("ix_surface_component_analysis_items_program_id", "surface_component_analysis_items", ["program_id"])
    op.create_index("ix_surface_component_analysis_items_snapshot_id", "surface_component_analysis_items", ["snapshot_id"])
    op.create_index("idx_surface_component_analysis_items_priority", "surface_component_analysis_items", ["snapshot_id", "exploration_priority_score", "structural_pressure_score"])


def downgrade() -> None:
    op.drop_index("idx_surface_component_analysis_items_priority", table_name="surface_component_analysis_items")
    op.drop_index("ix_surface_component_analysis_items_snapshot_id", table_name="surface_component_analysis_items")
    op.drop_index("ix_surface_component_analysis_items_program_id", table_name="surface_component_analysis_items")
    op.drop_index("ix_surface_component_analysis_items_analysis_run_id", table_name="surface_component_analysis_items")
    op.drop_table("surface_component_analysis_items")

    op.drop_index("idx_surface_component_analysis_runs_program_snapshot", table_name="surface_component_analysis_runs")
    op.drop_index("ix_surface_component_analysis_runs_snapshot_id", table_name="surface_component_analysis_runs")
    op.drop_index("ix_surface_component_analysis_runs_program_id", table_name="surface_component_analysis_runs")
    op.drop_table("surface_component_analysis_runs")
