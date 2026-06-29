"""Add bounded raw artifact previews and sanitizer state.

Revision ID: i5j6k7l8m9n0
Revises: h4i5j6k7l8m9
"""

from alembic import op
import sqlalchemy as sa


revision = "i5j6k7l8m9n0"
down_revision = "h4i5j6k7l8m9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("raw_artifacts", sa.Column("preview", sa.Text(), nullable=True))
    op.add_column(
        "raw_artifacts",
        sa.Column("sanitized_preview", sa.Text(), nullable=True),
    )
    op.add_column(
        "raw_artifacts",
        sa.Column("sanitizer_version", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "raw_artifacts",
        sa.Column("redaction_policy_version", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "raw_artifacts",
        sa.Column(
            "raw_safe_for_llm",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "raw_artifacts",
        sa.Column(
            "sanitized_safe_for_llm",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    op.execute("UPDATE raw_artifacts SET raw_safe_for_llm = false")
    op.create_check_constraint(
        "ck_raw_artifacts_sanitized_llm_requires_preview",
        "raw_artifacts",
        (
            "sanitized_safe_for_llm = false OR "
            "(sanitized_preview IS NOT NULL "
            "AND sanitizer_version IS NOT NULL "
            "AND redaction_policy_version IS NOT NULL)"
        ),
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_raw_artifacts_sanitized_llm_requires_preview",
        "raw_artifacts",
        type_="check",
    )
    op.drop_column("raw_artifacts", "sanitized_safe_for_llm")
    op.drop_column("raw_artifacts", "raw_safe_for_llm")
    op.drop_column("raw_artifacts", "redaction_policy_version")
    op.drop_column("raw_artifacts", "sanitizer_version")
    op.drop_column("raw_artifacts", "sanitized_preview")
    op.drop_column("raw_artifacts", "preview")
