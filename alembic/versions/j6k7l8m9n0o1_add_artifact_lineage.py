"""Add explicit raw artifact lineage fields.

Revision ID: j6k7l8m9n0o1
Revises: i5j6k7l8m9n0
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "j6k7l8m9n0o1"
down_revision = "i5j6k7l8m9n0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "raw_artifacts",
        sa.Column(
            "parser_name",
            sa.String(length=150),
            nullable=False,
            server_default="unknown",
        ),
    )
    op.add_column(
        "raw_artifacts",
        sa.Column(
            "parser_version",
            sa.String(length=100),
            nullable=False,
            server_default="1",
        ),
    )
    op.add_column(
        "raw_artifacts",
        sa.Column("scope_decision_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "raw_artifacts",
        sa.Column(
            "source_targets",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "raw_artifacts",
        sa.Column("parent_artifact_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute(
        """
        UPDATE raw_artifacts
        SET source_targets = COALESCE(artifact_metadata -> 'targets', '[]'::jsonb)
        """
    )
    op.create_foreign_key(
        "raw_artifacts_scope_decision_id_fkey",
        "raw_artifacts",
        "scope_decisions",
        ["scope_decision_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "raw_artifacts_parent_artifact_id_fkey",
        "raw_artifacts",
        "raw_artifacts",
        ["parent_artifact_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_raw_artifacts_scope_decision_id",
        "raw_artifacts",
        ["scope_decision_id"],
    )
    op.create_index(
        "ix_raw_artifacts_parent_artifact_id",
        "raw_artifacts",
        ["parent_artifact_id"],
    )
    op.create_check_constraint(
        "ck_raw_artifacts_parser_name_not_empty",
        "raw_artifacts",
        "parser_name != ''",
    )
    op.create_check_constraint(
        "ck_raw_artifacts_parser_version_not_empty",
        "raw_artifacts",
        "parser_version != ''",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_raw_artifacts_parser_version_not_empty",
        "raw_artifacts",
        type_="check",
    )
    op.drop_constraint(
        "ck_raw_artifacts_parser_name_not_empty",
        "raw_artifacts",
        type_="check",
    )
    op.drop_index(
        "ix_raw_artifacts_parent_artifact_id",
        table_name="raw_artifacts",
    )
    op.drop_index(
        "ix_raw_artifacts_scope_decision_id",
        table_name="raw_artifacts",
    )
    op.drop_constraint(
        "raw_artifacts_parent_artifact_id_fkey",
        "raw_artifacts",
        type_="foreignkey",
    )
    op.drop_constraint(
        "raw_artifacts_scope_decision_id_fkey",
        "raw_artifacts",
        type_="foreignkey",
    )
    op.drop_column("raw_artifacts", "parent_artifact_id")
    op.drop_column("raw_artifacts", "source_targets")
    op.drop_column("raw_artifacts", "scope_decision_id")
    op.drop_column("raw_artifacts", "parser_version")
    op.drop_column("raw_artifacts", "parser_name")
