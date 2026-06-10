"""Add surface map bounded context tables.

Revision ID: u1v2w3x4y5z6
Revises: t0u1v2w3x4y5
Create Date: 2026-06-10 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "u1v2w3x4y5z6"
down_revision: Union[str, None] = "t0u1v2w3x4y5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


JSONB = postgresql.JSONB(astext_type=sa.Text())
UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "surface_snapshots",
        sa.Column("id", UUID, nullable=False),
        sa.Column("program_id", UUID, nullable=False),
        sa.Column("snapshot_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("algorithm", sa.String(length=100), nullable=False),
        sa.Column("algorithm_version", sa.String(length=100), nullable=False),
        sa.Column("source_window_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_window_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("input_watermark", sa.Text(), nullable=True),
        sa.Column("stats_json", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("snapshot_fingerprint != ''", name="ck_surface_snapshots_fingerprint_not_empty"),
        sa.CheckConstraint("algorithm != ''", name="ck_surface_snapshots_algorithm_not_empty"),
        sa.CheckConstraint("algorithm_version != ''", name="ck_surface_snapshots_algorithm_version_not_empty"),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("program_id", "snapshot_fingerprint", name="uq_surface_snapshots_program_fingerprint"),
    )
    op.create_index("ix_surface_snapshots_program_id", "surface_snapshots", ["program_id"])
    op.create_index("idx_surface_snapshots_program_created", "surface_snapshots", ["program_id", "created_at"])

    op.create_table(
        "surface_nodes",
        sa.Column("id", UUID, nullable=False),
        sa.Column("program_id", UUID, nullable=False),
        sa.Column("snapshot_id", UUID, nullable=False),
        sa.Column("node_type", sa.String(length=50), nullable=False),
        sa.Column("ref_type", sa.String(length=50), nullable=True),
        sa.Column("ref_id", sa.Text(), nullable=True),
        sa.Column("node_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("feature_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("feature_version", sa.String(length=100), nullable=False),
        sa.Column("host", sa.Text(), nullable=True),
        sa.Column("path", sa.Text(), nullable=True),
        sa.Column("route_template", sa.Text(), nullable=True),
        sa.Column("method", sa.String(length=10), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("content_type", sa.Text(), nullable=True),
        sa.Column("features_json", JSONB, nullable=False),
        sa.Column("safe_for_search", sa.Boolean(), nullable=False),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("node_type != ''", name="ck_surface_nodes_node_type_not_empty"),
        sa.CheckConstraint("node_fingerprint != ''", name="ck_surface_nodes_fingerprint_not_empty"),
        sa.CheckConstraint("feature_fingerprint != ''", name="ck_surface_nodes_feature_fingerprint_not_empty"),
        sa.CheckConstraint("feature_version != ''", name="ck_surface_nodes_feature_version_not_empty"),
        sa.CheckConstraint("ref_type IS NULL OR ref_type != ''", name="ck_surface_nodes_ref_type_not_empty"),
        sa.CheckConstraint("ref_id IS NULL OR ref_id != ''", name="ck_surface_nodes_ref_id_not_empty"),
        sa.CheckConstraint("status_code IS NULL OR (status_code >= 100 AND status_code <= 599)", name="ck_surface_nodes_status_code_range"),
        sa.CheckConstraint("last_seen IS NULL OR first_seen IS NULL OR last_seen >= first_seen", name="ck_surface_nodes_seen_range"),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["surface_snapshots.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("program_id", "snapshot_id", "node_fingerprint", name="uq_surface_nodes_snapshot_fingerprint"),
    )
    op.create_index("ix_surface_nodes_program_id", "surface_nodes", ["program_id"])
    op.create_index("ix_surface_nodes_snapshot_id", "surface_nodes", ["snapshot_id"])
    op.create_index("ix_surface_nodes_node_type", "surface_nodes", ["node_type"])
    op.create_index("ix_surface_nodes_feature_fingerprint", "surface_nodes", ["feature_fingerprint"])
    op.create_index("idx_surface_nodes_program_snapshot_type", "surface_nodes", ["program_id", "snapshot_id", "node_type"])
    op.create_index("idx_surface_nodes_program_host", "surface_nodes", ["program_id", "host"])
    op.create_index("idx_surface_nodes_program_route", "surface_nodes", ["program_id", "route_template"])

    op.create_table(
        "surface_edges",
        sa.Column("id", UUID, nullable=False),
        sa.Column("program_id", UUID, nullable=False),
        sa.Column("snapshot_id", UUID, nullable=False),
        sa.Column("src_node_id", UUID, nullable=False),
        sa.Column("dst_node_id", UUID, nullable=False),
        sa.Column("edge_type", sa.String(length=80), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("edge_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("algorithm_version", sa.String(length=100), nullable=False),
        sa.Column("evidence_json", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("edge_type != ''", name="ck_surface_edges_type_not_empty"),
        sa.CheckConstraint("edge_fingerprint != ''", name="ck_surface_edges_fingerprint_not_empty"),
        sa.CheckConstraint("algorithm_version != ''", name="ck_surface_edges_algorithm_version_not_empty"),
        sa.CheckConstraint("weight >= 0 AND weight <= 1", name="ck_surface_edges_weight_range"),
        sa.CheckConstraint("src_node_id != dst_node_id", name="ck_surface_edges_no_self_edge"),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["surface_snapshots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["src_node_id"], ["surface_nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dst_node_id"], ["surface_nodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("program_id", "snapshot_id", "edge_fingerprint", name="uq_surface_edges_snapshot_fingerprint"),
    )
    op.create_index("ix_surface_edges_program_id", "surface_edges", ["program_id"])
    op.create_index("ix_surface_edges_snapshot_id", "surface_edges", ["snapshot_id"])
    op.create_index("ix_surface_edges_src_node_id", "surface_edges", ["src_node_id"])
    op.create_index("ix_surface_edges_dst_node_id", "surface_edges", ["dst_node_id"])
    op.create_index("ix_surface_edges_edge_type", "surface_edges", ["edge_type"])
    op.create_index("idx_surface_edges_program_snapshot_type", "surface_edges", ["program_id", "snapshot_id", "edge_type"])

    op.create_table(
        "surface_clusters",
        sa.Column("id", UUID, nullable=False),
        sa.Column("program_id", UUID, nullable=False),
        sa.Column("snapshot_id", UUID, nullable=False),
        sa.Column("cluster_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("algorithm", sa.String(length=100), nullable=False),
        sa.Column("algorithm_version", sa.String(length=100), nullable=False),
        sa.Column("member_count", sa.Integer(), nullable=False),
        sa.Column("score_json", JSONB, nullable=False),
        sa.Column("summary_json", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("cluster_fingerprint != ''", name="ck_surface_clusters_fingerprint_not_empty"),
        sa.CheckConstraint("algorithm != ''", name="ck_surface_clusters_algorithm_not_empty"),
        sa.CheckConstraint("algorithm_version != ''", name="ck_surface_clusters_algorithm_version_not_empty"),
        sa.CheckConstraint("member_count >= 0", name="ck_surface_clusters_member_count_non_negative"),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["surface_snapshots.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("program_id", "snapshot_id", "cluster_fingerprint", name="uq_surface_clusters_snapshot_fingerprint"),
    )
    op.create_index("ix_surface_clusters_program_id", "surface_clusters", ["program_id"])
    op.create_index("ix_surface_clusters_snapshot_id", "surface_clusters", ["snapshot_id"])
    op.create_index("idx_surface_clusters_program_snapshot", "surface_clusters", ["program_id", "snapshot_id"])

    op.create_table(
        "surface_cluster_members",
        sa.Column("cluster_id", UUID, nullable=False),
        sa.Column("node_id", UUID, nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("role != ''", name="ck_surface_cluster_members_role_not_empty"),
        sa.CheckConstraint("weight >= 0 AND weight <= 1", name="ck_surface_cluster_members_weight_range"),
        sa.ForeignKeyConstraint(["cluster_id"], ["surface_clusters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["node_id"], ["surface_nodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("cluster_id", "node_id"),
    )
    op.create_index("ix_surface_cluster_members_cluster_id", "surface_cluster_members", ["cluster_id"])
    op.create_index("ix_surface_cluster_members_node_id", "surface_cluster_members", ["node_id"])

    op.create_table(
        "surface_cluster_labels",
        sa.Column("id", UUID, nullable=False),
        sa.Column("cluster_id", UUID, nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("label_source", sa.String(length=50), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("risk_tags_json", JSONB, nullable=False),
        sa.Column("evidence_refs", JSONB, nullable=False),
        sa.Column("model_version", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("label != ''", name="ck_surface_cluster_labels_label_not_empty"),
        sa.CheckConstraint("label_source != ''", name="ck_surface_cluster_labels_source_not_empty"),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_surface_cluster_labels_confidence_range"),
        sa.CheckConstraint("status IN ('proposed', 'confirmed', 'rejected', 'merged', 'stale')", name="ck_surface_cluster_labels_status_valid"),
        sa.CheckConstraint("label_source IN ('fixture', 'llm', 'manual', 'system')", name="ck_surface_cluster_labels_source_valid"),
        sa.ForeignKeyConstraint(["cluster_id"], ["surface_clusters.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cluster_id", "label", "label_source", name="uq_surface_cluster_labels_cluster_label_source"),
    )
    op.create_index("ix_surface_cluster_labels_cluster_id", "surface_cluster_labels", ["cluster_id"])
    op.create_index("ix_surface_cluster_labels_label", "surface_cluster_labels", ["label"])
    op.create_index("ix_surface_cluster_labels_status", "surface_cluster_labels", ["status"])

    op.create_table(
        "surface_deltas",
        sa.Column("id", UUID, nullable=False),
        sa.Column("program_id", UUID, nullable=False),
        sa.Column("from_snapshot_id", UUID, nullable=True),
        sa.Column("to_snapshot_id", UUID, nullable=False),
        sa.Column("delta_type", sa.String(length=100), nullable=False),
        sa.Column("subject_type", sa.String(length=50), nullable=False),
        sa.Column("subject_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("novelty_score", sa.Integer(), nullable=False),
        sa.Column("details_json", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("delta_type != ''", name="ck_surface_deltas_type_not_empty"),
        sa.CheckConstraint("subject_type != ''", name="ck_surface_deltas_subject_type_not_empty"),
        sa.CheckConstraint("subject_fingerprint != ''", name="ck_surface_deltas_subject_fingerprint_not_empty"),
        sa.CheckConstraint("novelty_score >= 0 AND novelty_score <= 100", name="ck_surface_deltas_novelty_score_range"),
        sa.CheckConstraint("from_snapshot_id IS NULL OR from_snapshot_id != to_snapshot_id", name="ck_surface_deltas_distinct_snapshots"),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["from_snapshot_id"], ["surface_snapshots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["to_snapshot_id"], ["surface_snapshots.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("program_id", "to_snapshot_id", "delta_type", "subject_fingerprint", name="uq_surface_deltas_snapshot_type_subject"),
    )
    op.create_index("ix_surface_deltas_program_id", "surface_deltas", ["program_id"])
    op.create_index("ix_surface_deltas_from_snapshot_id", "surface_deltas", ["from_snapshot_id"])
    op.create_index("ix_surface_deltas_to_snapshot_id", "surface_deltas", ["to_snapshot_id"])
    op.create_index("ix_surface_deltas_delta_type", "surface_deltas", ["delta_type"])
    op.create_index("idx_surface_deltas_program_to_snapshot", "surface_deltas", ["program_id", "to_snapshot_id"])


def downgrade() -> None:
    op.drop_index("idx_surface_deltas_program_to_snapshot", table_name="surface_deltas")
    op.drop_index("ix_surface_deltas_delta_type", table_name="surface_deltas")
    op.drop_index("ix_surface_deltas_to_snapshot_id", table_name="surface_deltas")
    op.drop_index("ix_surface_deltas_from_snapshot_id", table_name="surface_deltas")
    op.drop_index("ix_surface_deltas_program_id", table_name="surface_deltas")
    op.drop_table("surface_deltas")

    op.drop_index("ix_surface_cluster_labels_status", table_name="surface_cluster_labels")
    op.drop_index("ix_surface_cluster_labels_label", table_name="surface_cluster_labels")
    op.drop_index("ix_surface_cluster_labels_cluster_id", table_name="surface_cluster_labels")
    op.drop_table("surface_cluster_labels")

    op.drop_index("ix_surface_cluster_members_node_id", table_name="surface_cluster_members")
    op.drop_index("ix_surface_cluster_members_cluster_id", table_name="surface_cluster_members")
    op.drop_table("surface_cluster_members")

    op.drop_index("idx_surface_clusters_program_snapshot", table_name="surface_clusters")
    op.drop_index("ix_surface_clusters_snapshot_id", table_name="surface_clusters")
    op.drop_index("ix_surface_clusters_program_id", table_name="surface_clusters")
    op.drop_table("surface_clusters")

    op.drop_index("idx_surface_edges_program_snapshot_type", table_name="surface_edges")
    op.drop_index("ix_surface_edges_edge_type", table_name="surface_edges")
    op.drop_index("ix_surface_edges_dst_node_id", table_name="surface_edges")
    op.drop_index("ix_surface_edges_src_node_id", table_name="surface_edges")
    op.drop_index("ix_surface_edges_snapshot_id", table_name="surface_edges")
    op.drop_index("ix_surface_edges_program_id", table_name="surface_edges")
    op.drop_table("surface_edges")

    op.drop_index("idx_surface_nodes_program_route", table_name="surface_nodes")
    op.drop_index("idx_surface_nodes_program_host", table_name="surface_nodes")
    op.drop_index("idx_surface_nodes_program_snapshot_type", table_name="surface_nodes")
    op.drop_index("ix_surface_nodes_feature_fingerprint", table_name="surface_nodes")
    op.drop_index("ix_surface_nodes_node_type", table_name="surface_nodes")
    op.drop_index("ix_surface_nodes_snapshot_id", table_name="surface_nodes")
    op.drop_index("ix_surface_nodes_program_id", table_name="surface_nodes")
    op.drop_table("surface_nodes")

    op.drop_index("idx_surface_snapshots_program_created", table_name="surface_snapshots")
    op.drop_index("ix_surface_snapshots_program_id", table_name="surface_snapshots")
    op.drop_table("surface_snapshots")
