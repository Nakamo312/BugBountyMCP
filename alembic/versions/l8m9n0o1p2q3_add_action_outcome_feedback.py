"""Add action outcome feedback audit trail.

Revision ID: l8m9n0o1p2q3
Revises: k7l8m9n0o1p2
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "l8m9n0o1p2q3"
down_revision = "k7l8m9n0o1p2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "action_outcome_feedback_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("outcome_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("program_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("manual_interest", sa.Boolean(), nullable=True),
        sa.Column("manual_stop", sa.Boolean(), nullable=True),
        sa.Column("continued_by_followup", sa.Boolean(), nullable=True),
        sa.Column("report_created", sa.Boolean(), nullable=True),
        sa.Column("triage_outcome", sa.String(length=100), nullable=True),
        sa.Column("actor", sa.String(length=150), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["outcome_id"], ["action_outcomes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["action_id"], ["action_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("actor != ''", name="ck_action_outcome_feedback_actor_not_empty"),
        sa.CheckConstraint("source != ''", name="ck_action_outcome_feedback_source_not_empty"),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_action_outcome_feedback_confidence_range",
        ),
        sa.CheckConstraint(
            "manual_interest IS NOT NULL OR manual_stop IS NOT NULL OR "
            "continued_by_followup IS NOT NULL OR report_created IS NOT NULL OR "
            "triage_outcome IS NOT NULL",
            name="ck_action_outcome_feedback_has_signal",
        ),
        sa.CheckConstraint(
            "triage_outcome IS NULL OR triage_outcome != ''",
            name="ck_action_outcome_feedback_triage_not_empty",
        ),
    )
    op.create_index("ix_action_outcome_feedback_events_outcome_id", "action_outcome_feedback_events", ["outcome_id"])
    op.create_index("ix_action_outcome_feedback_events_program_id", "action_outcome_feedback_events", ["program_id"])
    op.create_index("ix_action_outcome_feedback_events_campaign_id", "action_outcome_feedback_events", ["campaign_id"])
    op.create_index("ix_action_outcome_feedback_events_action_id", "action_outcome_feedback_events", ["action_id"])
    op.create_index("ix_action_outcome_feedback_events_job_id", "action_outcome_feedback_events", ["job_id"])
    op.create_index("ix_action_outcome_feedback_events_run_id", "action_outcome_feedback_events", ["run_id"])
    op.create_index(
        "idx_action_outcome_feedback_action_created",
        "action_outcome_feedback_events",
        ["action_id", "created_at"],
    )
    op.create_index(
        "idx_action_outcome_feedback_run_created",
        "action_outcome_feedback_events",
        ["run_id", "created_at"],
    )
    op.create_index(
        "idx_action_outcome_feedback_outcome_created",
        "action_outcome_feedback_events",
        ["outcome_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_action_outcome_feedback_outcome_created", table_name="action_outcome_feedback_events")
    op.drop_index("idx_action_outcome_feedback_run_created", table_name="action_outcome_feedback_events")
    op.drop_index("idx_action_outcome_feedback_action_created", table_name="action_outcome_feedback_events")
    op.drop_index("ix_action_outcome_feedback_events_run_id", table_name="action_outcome_feedback_events")
    op.drop_index("ix_action_outcome_feedback_events_job_id", table_name="action_outcome_feedback_events")
    op.drop_index("ix_action_outcome_feedback_events_action_id", table_name="action_outcome_feedback_events")
    op.drop_index("ix_action_outcome_feedback_events_campaign_id", table_name="action_outcome_feedback_events")
    op.drop_index("ix_action_outcome_feedback_events_program_id", table_name="action_outcome_feedback_events")
    op.drop_index("ix_action_outcome_feedback_events_outcome_id", table_name="action_outcome_feedback_events")
    op.drop_table("action_outcome_feedback_events")
