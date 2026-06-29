"""Add raw artifact compression and retention metadata.

Revision ID: h4i5j6k7l8m9
Revises: g3h4i5j6k7l8
"""

from alembic import op
import sqlalchemy as sa


revision = "h4i5j6k7l8m9"
down_revision = "g3h4i5j6k7l8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "raw_artifacts",
        sa.Column(
            "storage_size_bytes",
            sa.Integer(),
            nullable=True,
            server_default="0",
        ),
    )
    op.add_column(
        "raw_artifacts",
        sa.Column(
            "content_encoding",
            sa.String(length=20),
            nullable=False,
            server_default="identity",
        ),
    )
    op.add_column(
        "raw_artifacts",
        sa.Column(
            "retention_class",
            sa.String(length=30),
            nullable=False,
            server_default="program_lifetime",
        ),
    )
    op.execute(
        "UPDATE raw_artifacts SET storage_size_bytes = size_bytes "
        "WHERE storage_size_bytes IS NULL"
    )
    op.alter_column("raw_artifacts", "storage_size_bytes", nullable=False)
    op.create_index(
        "idx_raw_artifacts_retention_class",
        "raw_artifacts",
        ["retention_class"],
    )
    op.create_check_constraint(
        "ck_raw_artifacts_storage_size_non_negative",
        "raw_artifacts",
        "storage_size_bytes >= 0",
    )
    op.create_check_constraint(
        "ck_raw_artifacts_content_encoding_valid",
        "raw_artifacts",
        "content_encoding IN ('identity', 'gzip')",
    )
    op.create_check_constraint(
        "ck_raw_artifacts_retention_class_valid",
        "raw_artifacts",
        (
            "retention_class IN "
            "('ephemeral', 'short_lived', 'program_lifetime', 'legal_hold')"
        ),
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_raw_artifacts_retention_class_valid",
        "raw_artifacts",
        type_="check",
    )
    op.drop_constraint(
        "ck_raw_artifacts_content_encoding_valid",
        "raw_artifacts",
        type_="check",
    )
    op.drop_constraint(
        "ck_raw_artifacts_storage_size_non_negative",
        "raw_artifacts",
        type_="check",
    )
    op.drop_index(
        "idx_raw_artifacts_retention_class",
        table_name="raw_artifacts",
    )
    op.drop_column("raw_artifacts", "retention_class")
    op.drop_column("raw_artifacts", "content_encoding")
    op.drop_column("raw_artifacts", "storage_size_bytes")
