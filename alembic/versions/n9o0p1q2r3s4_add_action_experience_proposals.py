"""Persist internal action experience proposals.

Revision ID: n9o0p1q2r3s4
Revises: m9n0o1p2q3r4
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "n9o0p1q2r3s4"
down_revision = "m9n0o1p2q3r4"
branch_labels = None
depends_on = None


RUN_STATUSES = "('completed', 'no_candidates', 'failed')"
PROPOSAL_STATUSES = "('pending', 'accepted', 'rejected', 'suppressed', 'expired')"


def upgrade() -> None:
    op.create_table(
        "action_experience_proposal_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("program_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_outcome_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_action_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("candidate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("feature_builder_version", sa.String(length=100), nullable=False),
        sa.Column("feature_keys", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("graph_counts", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("produced_by", sa.String(length=100), nullable=False, server_default="action-experience-proposal-worker"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_outcome_id"], ["action_outcomes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_action_id"], ["action_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_outcome_id", name="uq_action_experience_proposal_runs_source"),
        sa.CheckConstraint(f"status IN {RUN_STATUSES}", name="ck_action_experience_proposal_runs_status_valid"),
        sa.CheckConstraint("candidate_count >= 0", name="ck_action_experience_proposal_runs_candidate_count_nonnegative"),
        sa.CheckConstraint("feature_builder_version != ''", name="ck_action_experience_proposal_runs_builder_not_empty"),
        sa.CheckConstraint("produced_by != ''", name="ck_action_experience_proposal_runs_producer_not_empty"),
    )
    op.create_index("ix_action_experience_proposal_runs_program_id", "action_experience_proposal_runs", ["program_id"])
    op.create_index("ix_action_experience_proposal_runs_campaign_id", "action_experience_proposal_runs", ["campaign_id"])
    op.create_index("ix_action_experience_proposal_runs_source_run_id", "action_experience_proposal_runs", ["source_run_id"])
    op.create_index(
        "idx_action_experience_proposal_runs_status_created",
        "action_experience_proposal_runs",
        ["status", "created_at"],
    )

    op.create_table(
        "action_experience_proposals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("proposal_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("program_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_outcome_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_action_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("proposal_key", sa.String(length=300), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("capability_id", sa.String(length=100), nullable=False),
        sa.Column("profile_id", sa.String(length=100), nullable=False),
        sa.Column("utility_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("sample_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_similarity", sa.Float(), nullable=False, server_default="0"),
        sa.Column("avg_information_gain_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("human_positive_rate", sa.Float(), nullable=False, server_default="0"),
        sa.Column("human_stop_rate", sa.Float(), nullable=False, server_default="0"),
        sa.Column("explanation", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("produced_by", sa.String(length=100), nullable=False, server_default="action-experience-proposal-worker"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["proposal_run_id"], ["action_experience_proposal_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_outcome_id"], ["action_outcomes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_action_id"], ["action_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("proposal_key", name="uq_action_experience_proposals_key"),
        sa.CheckConstraint("proposal_key != ''", name="ck_action_experience_proposals_key_not_empty"),
        sa.CheckConstraint(f"status IN {PROPOSAL_STATUSES}", name="ck_action_experience_proposals_status_valid"),
        sa.CheckConstraint("rank > 0", name="ck_action_experience_proposals_rank_positive"),
        sa.CheckConstraint("capability_id != ''", name="ck_action_experience_proposals_capability_not_empty"),
        sa.CheckConstraint("profile_id != ''", name="ck_action_experience_proposals_profile_not_empty"),
        sa.CheckConstraint("utility_score >= 0", name="ck_action_experience_proposals_utility_nonnegative"),
        sa.CheckConstraint("sample_count >= 0", name="ck_action_experience_proposals_sample_count_nonnegative"),
        sa.CheckConstraint("avg_similarity >= 0 AND avg_similarity <= 1", name="ck_action_experience_proposals_similarity_range"),
        sa.CheckConstraint("human_positive_rate >= 0 AND human_positive_rate <= 1", name="ck_action_experience_proposals_positive_rate_range"),
        sa.CheckConstraint("human_stop_rate >= 0 AND human_stop_rate <= 1", name="ck_action_experience_proposals_stop_rate_range"),
        sa.CheckConstraint("produced_by != ''", name="ck_action_experience_proposals_producer_not_empty"),
    )
    op.create_index("ix_action_experience_proposals_program_id", "action_experience_proposals", ["program_id"])
    op.create_index("ix_action_experience_proposals_campaign_id", "action_experience_proposals", ["campaign_id"])
    op.create_index("ix_action_experience_proposals_proposal_run_id", "action_experience_proposals", ["proposal_run_id"])
    op.create_index("ix_action_experience_proposals_source_outcome_id", "action_experience_proposals", ["source_outcome_id"])
    op.create_index("ix_action_experience_proposals_source_run_id", "action_experience_proposals", ["source_run_id"])
    op.create_index(
        "idx_action_experience_proposals_pending_program_rank",
        "action_experience_proposals",
        ["program_id", "status", "rank", "created_at"],
    )
    op.create_index(
        "idx_action_experience_proposals_campaign_status",
        "action_experience_proposals",
        ["campaign_id", "status", "utility_score"],
    )
    op.create_index(
        "idx_action_experience_proposals_capability_profile",
        "action_experience_proposals",
        ["capability_id", "profile_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_action_experience_proposals_capability_profile", table_name="action_experience_proposals")
    op.drop_index("idx_action_experience_proposals_campaign_status", table_name="action_experience_proposals")
    op.drop_index("idx_action_experience_proposals_pending_program_rank", table_name="action_experience_proposals")
    op.drop_index("ix_action_experience_proposals_source_run_id", table_name="action_experience_proposals")
    op.drop_index("ix_action_experience_proposals_source_outcome_id", table_name="action_experience_proposals")
    op.drop_index("ix_action_experience_proposals_proposal_run_id", table_name="action_experience_proposals")
    op.drop_index("ix_action_experience_proposals_campaign_id", table_name="action_experience_proposals")
    op.drop_index("ix_action_experience_proposals_program_id", table_name="action_experience_proposals")
    op.drop_table("action_experience_proposals")
    op.drop_index("idx_action_experience_proposal_runs_status_created", table_name="action_experience_proposal_runs")
    op.drop_index("ix_action_experience_proposal_runs_source_run_id", table_name="action_experience_proposal_runs")
    op.drop_index("ix_action_experience_proposal_runs_campaign_id", table_name="action_experience_proposal_runs")
    op.drop_index("ix_action_experience_proposal_runs_program_id", table_name="action_experience_proposal_runs")
    op.drop_table("action_experience_proposal_runs")
