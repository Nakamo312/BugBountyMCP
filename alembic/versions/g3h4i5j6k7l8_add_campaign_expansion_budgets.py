"""Add bounded campaign expansion budgets.

Revision ID: g3h4i5j6k7l8
Revises: f2g3h4i5j6k7
"""

from alembic import op
import sqlalchemy as sa


revision = "g3h4i5j6k7l8"
down_revision = "f2g3h4i5j6k7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "campaigns",
        sa.Column("max_runs", sa.Integer(), nullable=False, server_default="1000"),
    )
    op.add_column(
        "campaigns",
        sa.Column("max_targets", sa.Integer(), nullable=False, server_default="100000"),
    )
    op.add_column(
        "campaigns",
        sa.Column("runs_consumed", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "campaigns",
        sa.Column("targets_consumed", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "campaigns",
        sa.Column(
            "token_capacity",
            sa.Float(),
            nullable=False,
            server_default="100.0",
        ),
    )
    op.add_column(
        "campaigns",
        sa.Column(
            "tokens_available",
            sa.Float(),
            nullable=False,
            server_default="100.0",
        ),
    )
    op.add_column(
        "campaigns",
        sa.Column(
            "token_refill_per_second",
            sa.Float(),
            nullable=False,
            server_default="1.0",
        ),
    )
    op.add_column(
        "campaigns",
        sa.Column(
            "tokens_refilled_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_check_constraint(
        "ck_campaigns_max_runs_positive",
        "campaigns",
        "max_runs > 0",
    )
    op.create_check_constraint(
        "ck_campaigns_max_targets_positive",
        "campaigns",
        "max_targets > 0",
    )
    op.create_check_constraint(
        "ck_campaigns_runs_consumed_nonnegative",
        "campaigns",
        "runs_consumed >= 0",
    )
    op.create_check_constraint(
        "ck_campaigns_targets_consumed_nonnegative",
        "campaigns",
        "targets_consumed >= 0",
    )
    op.create_check_constraint(
        "ck_campaigns_token_capacity_positive",
        "campaigns",
        "token_capacity > 0",
    )
    op.create_check_constraint(
        "ck_campaigns_tokens_available_nonnegative",
        "campaigns",
        "tokens_available >= 0 AND tokens_available <= token_capacity",
    )
    op.create_check_constraint(
        "ck_campaigns_token_refill_positive",
        "campaigns",
        "token_refill_per_second > 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_campaigns_token_refill_positive",
        "campaigns",
        type_="check",
    )
    op.drop_constraint(
        "ck_campaigns_tokens_available_nonnegative",
        "campaigns",
        type_="check",
    )
    op.drop_constraint(
        "ck_campaigns_token_capacity_positive",
        "campaigns",
        type_="check",
    )
    op.drop_constraint(
        "ck_campaigns_targets_consumed_nonnegative",
        "campaigns",
        type_="check",
    )
    op.drop_constraint(
        "ck_campaigns_runs_consumed_nonnegative",
        "campaigns",
        type_="check",
    )
    op.drop_constraint(
        "ck_campaigns_max_targets_positive",
        "campaigns",
        type_="check",
    )
    op.drop_constraint(
        "ck_campaigns_max_runs_positive",
        "campaigns",
        type_="check",
    )
    op.drop_column("campaigns", "tokens_refilled_at")
    op.drop_column("campaigns", "token_refill_per_second")
    op.drop_column("campaigns", "tokens_available")
    op.drop_column("campaigns", "token_capacity")
    op.drop_column("campaigns", "targets_consumed")
    op.drop_column("campaigns", "runs_consumed")
    op.drop_column("campaigns", "max_targets")
    op.drop_column("campaigns", "max_runs")
