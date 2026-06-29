"""Add action outcome memory.

Revision ID: k7l8m9n0o1p2
Revises: j6k7l8m9n0o1
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "k7l8m9n0o1p2"
down_revision = "j6k7l8m9n0o1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "action_outcomes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("program_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("capability_id", sa.String(length=100), nullable=False),
        sa.Column("profile_id", sa.String(length=100), nullable=False),
        sa.Column("node_id", sa.String(length=100), nullable=True),
        sa.Column("event_name", sa.String(length=150), nullable=True),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("terminal_outcome", sa.String(length=50), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("target_count", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("raw_artifact_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("raw_artifact_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("observed_hosts_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("observed_services_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("observed_endpoints_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("http_observation_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("javascript_reference_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_hosts_count", sa.Integer(), nullable=True),
        sa.Column("new_services_count", sa.Integer(), nullable=True),
        sa.Column("new_endpoints_count", sa.Integer(), nullable=True),
        sa.Column("before_surface_snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("after_surface_snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("new_surface_nodes_count", sa.Integer(), nullable=True),
        sa.Column("new_surface_edges_count", sa.Integer(), nullable=True),
        sa.Column("new_surface_clusters_count", sa.Integer(), nullable=True),
        sa.Column("new_surface_deltas_count", sa.Integer(), nullable=True),
        sa.Column("new_graph_facts_count", sa.Integer(), nullable=True),
        sa.Column("new_search_documents_count", sa.Integer(), nullable=True),
        sa.Column("manual_interest", sa.Boolean(), nullable=True),
        sa.Column("manual_stop", sa.Boolean(), nullable=True),
        sa.Column("continued_by_followup", sa.Boolean(), nullable=True),
        sa.Column("report_created", sa.Boolean(), nullable=True),
        sa.Column("triage_outcome", sa.String(length=100), nullable=True),
        sa.Column("information_gain_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("score_version", sa.String(length=100), nullable=False),
        sa.Column("score_breakdown", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["action_id"], ["action_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", name="uq_action_outcomes_run_id"),
        sa.CheckConstraint("capability_id != ''", name="ck_action_outcomes_capability_not_empty"),
        sa.CheckConstraint("profile_id != ''", name="ck_action_outcomes_profile_not_empty"),
        sa.CheckConstraint("attempt > 0", name="ck_action_outcomes_attempt_positive"),
        sa.CheckConstraint("target_count IS NULL OR target_count >= 0", name="ck_action_outcomes_target_count_nonnegative"),
        sa.CheckConstraint("duration_ms IS NULL OR duration_ms >= 0", name="ck_action_outcomes_duration_nonnegative"),
        sa.CheckConstraint("error_count >= 0", name="ck_action_outcomes_error_count_nonnegative"),
        sa.CheckConstraint("raw_artifact_count >= 0", name="ck_action_outcomes_raw_artifact_count_nonnegative"),
        sa.CheckConstraint("raw_artifact_bytes >= 0", name="ck_action_outcomes_raw_artifact_bytes_nonnegative"),
        sa.CheckConstraint("observed_hosts_count >= 0", name="ck_action_outcomes_observed_hosts_nonnegative"),
        sa.CheckConstraint("observed_services_count >= 0", name="ck_action_outcomes_observed_services_nonnegative"),
        sa.CheckConstraint("observed_endpoints_count >= 0", name="ck_action_outcomes_observed_endpoints_nonnegative"),
        sa.CheckConstraint("http_observation_count >= 0", name="ck_action_outcomes_http_observation_nonnegative"),
        sa.CheckConstraint("javascript_reference_count >= 0", name="ck_action_outcomes_javascript_reference_nonnegative"),
        sa.CheckConstraint("new_hosts_count IS NULL OR new_hosts_count >= 0", name="ck_action_outcomes_new_hosts_nonnegative"),
        sa.CheckConstraint("new_services_count IS NULL OR new_services_count >= 0", name="ck_action_outcomes_new_services_nonnegative"),
        sa.CheckConstraint("new_endpoints_count IS NULL OR new_endpoints_count >= 0", name="ck_action_outcomes_new_endpoints_nonnegative"),
        sa.CheckConstraint("new_surface_nodes_count IS NULL OR new_surface_nodes_count >= 0", name="ck_action_outcomes_surface_nodes_nonnegative"),
        sa.CheckConstraint("new_surface_edges_count IS NULL OR new_surface_edges_count >= 0", name="ck_action_outcomes_surface_edges_nonnegative"),
        sa.CheckConstraint("new_surface_clusters_count IS NULL OR new_surface_clusters_count >= 0", name="ck_action_outcomes_surface_clusters_nonnegative"),
        sa.CheckConstraint("new_surface_deltas_count IS NULL OR new_surface_deltas_count >= 0", name="ck_action_outcomes_surface_deltas_nonnegative"),
        sa.CheckConstraint("new_graph_facts_count IS NULL OR new_graph_facts_count >= 0", name="ck_action_outcomes_graph_facts_nonnegative"),
        sa.CheckConstraint("new_search_documents_count IS NULL OR new_search_documents_count >= 0", name="ck_action_outcomes_search_documents_nonnegative"),
        sa.CheckConstraint("information_gain_score >= 0", name="ck_action_outcomes_score_nonnegative"),
        sa.CheckConstraint("score_version != ''", name="ck_action_outcomes_score_version_not_empty"),
        sa.CheckConstraint(
            "status IN ('queued', 'leased', 'running', 'flushing', 'completed', 'failed', 'dead', 'cancelled')",
            name="ck_action_outcomes_status_valid",
        ),
        sa.CheckConstraint(
            "terminal_outcome IS NULL OR terminal_outcome IN "
            "('completed', 'partial', 'tool_failed', 'skipped', 'policy_blocked')",
            name="ck_action_outcomes_terminal_outcome_valid",
        ),
    )
    op.create_index("ix_action_outcomes_program_id", "action_outcomes", ["program_id"])
    op.create_index("ix_action_outcomes_campaign_id", "action_outcomes", ["campaign_id"])
    op.create_index("ix_action_outcomes_action_id", "action_outcomes", ["action_id"])
    op.create_index("ix_action_outcomes_job_id", "action_outcomes", ["job_id"])
    op.create_index("ix_action_outcomes_run_id", "action_outcomes", ["run_id"])
    op.create_index("ix_action_outcomes_capability_id", "action_outcomes", ["capability_id"])
    op.create_index("ix_action_outcomes_profile_id", "action_outcomes", ["profile_id"])
    op.create_index("ix_action_outcomes_node_id", "action_outcomes", ["node_id"])
    op.create_index("ix_action_outcomes_event_name", "action_outcomes", ["event_name"])
    op.create_index("ix_action_outcomes_correlation_id", "action_outcomes", ["correlation_id"])
    op.create_index("ix_action_outcomes_status", "action_outcomes", ["status"])
    op.create_index("ix_action_outcomes_terminal_outcome", "action_outcomes", ["terminal_outcome"])
    op.create_index("idx_action_outcomes_program_score", "action_outcomes", ["program_id", "information_gain_score"])
    op.create_index("idx_action_outcomes_campaign_created", "action_outcomes", ["campaign_id", "created_at"])
    op.create_index("idx_action_outcomes_capability_profile", "action_outcomes", ["capability_id", "profile_id"])


def downgrade() -> None:
    op.drop_index("idx_action_outcomes_capability_profile", table_name="action_outcomes")
    op.drop_index("idx_action_outcomes_campaign_created", table_name="action_outcomes")
    op.drop_index("idx_action_outcomes_program_score", table_name="action_outcomes")
    op.drop_index("ix_action_outcomes_terminal_outcome", table_name="action_outcomes")
    op.drop_index("ix_action_outcomes_status", table_name="action_outcomes")
    op.drop_index("ix_action_outcomes_correlation_id", table_name="action_outcomes")
    op.drop_index("ix_action_outcomes_event_name", table_name="action_outcomes")
    op.drop_index("ix_action_outcomes_node_id", table_name="action_outcomes")
    op.drop_index("ix_action_outcomes_profile_id", table_name="action_outcomes")
    op.drop_index("ix_action_outcomes_capability_id", table_name="action_outcomes")
    op.drop_index("ix_action_outcomes_run_id", table_name="action_outcomes")
    op.drop_index("ix_action_outcomes_job_id", table_name="action_outcomes")
    op.drop_index("ix_action_outcomes_action_id", table_name="action_outcomes")
    op.drop_index("ix_action_outcomes_campaign_id", table_name="action_outcomes")
    op.drop_index("ix_action_outcomes_program_id", table_name="action_outcomes")
    op.drop_table("action_outcomes")
