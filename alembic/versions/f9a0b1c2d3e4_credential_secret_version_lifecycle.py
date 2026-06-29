"""Add credential secret version lifecycle metadata.

Revision ID: f9a0b1c2d3e4
Revises: e8f9a0b1c2d3
Create Date: 2026-06-28 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f9a0b1c2d3e4"
down_revision: Union[str, None] = "e8f9a0b1c2d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSONB = postgresql.JSONB(astext_type=sa.Text())
UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.add_column("credential_refs", sa.Column("current_secret_version_id", UUID, nullable=True))
    op.add_column(
        "credential_refs",
        sa.Column("refresh_policy_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.add_column(
        "credential_refs",
        sa.Column("refresh_status", sa.String(length=30), nullable=False, server_default="not_configured"),
    )
    op.add_column("credential_refs", sa.Column("last_refreshed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("credential_refs", sa.Column("next_refresh_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "fk_credential_refs_current_secret_version",
        "credential_refs",
        "credential_secret_versions",
        ["current_secret_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_credential_refs_refresh_status_valid",
        "credential_refs",
        "refresh_status IN ('not_configured', 'fresh', 'refresh_due', 'refresh_failed', 'disabled')",
    )
    op.create_index(
        "ix_credential_refs_current_secret_version_id",
        "credential_refs",
        ["current_secret_version_id"],
    )
    op.create_index("ix_credential_refs_refresh_status", "credential_refs", ["refresh_status"])
    op.create_index("ix_credential_refs_next_refresh_at", "credential_refs", ["next_refresh_at"])
    op.create_index(
        "idx_credential_refs_program_refresh",
        "credential_refs",
        ["program_id", "refresh_status", "next_refresh_at"],
    )

    op.add_column("credential_secret_versions", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("credential_secret_versions", sa.Column("replaced_by_version_id", UUID, nullable=True))
    op.create_foreign_key(
        "fk_credential_secret_versions_replaced_by",
        "credential_secret_versions",
        "credential_secret_versions",
        ["replaced_by_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.drop_constraint(
        "ck_credential_secret_versions_status_valid",
        "credential_secret_versions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_credential_secret_versions_status_valid",
        "credential_secret_versions",
        "status IN ('active', 'retired', 'expired', 'revoked')",
    )
    op.create_check_constraint(
        "ck_credential_secret_versions_not_self_replaced",
        "credential_secret_versions",
        "replaced_by_version_id IS NULL OR replaced_by_version_id != id",
    )
    op.create_index("ix_credential_secret_versions_expires_at", "credential_secret_versions", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_credential_secret_versions_expires_at", table_name="credential_secret_versions")
    op.drop_constraint(
        "ck_credential_secret_versions_not_self_replaced",
        "credential_secret_versions",
        type_="check",
    )
    op.drop_constraint(
        "ck_credential_secret_versions_status_valid",
        "credential_secret_versions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_credential_secret_versions_status_valid",
        "credential_secret_versions",
        "status IN ('active', 'retired', 'revoked')",
    )
    op.drop_constraint(
        "fk_credential_secret_versions_replaced_by",
        "credential_secret_versions",
        type_="foreignkey",
    )
    op.drop_column("credential_secret_versions", "replaced_by_version_id")
    op.drop_column("credential_secret_versions", "expires_at")

    op.drop_index("idx_credential_refs_program_refresh", table_name="credential_refs")
    op.drop_index("ix_credential_refs_next_refresh_at", table_name="credential_refs")
    op.drop_index("ix_credential_refs_refresh_status", table_name="credential_refs")
    op.drop_index("ix_credential_refs_current_secret_version_id", table_name="credential_refs")
    op.drop_constraint("ck_credential_refs_refresh_status_valid", "credential_refs", type_="check")
    op.drop_constraint("fk_credential_refs_current_secret_version", "credential_refs", type_="foreignkey")
    op.drop_column("credential_refs", "next_refresh_at")
    op.drop_column("credential_refs", "last_refreshed_at")
    op.drop_column("credential_refs", "refresh_status")
    op.drop_column("credential_refs", "refresh_policy_json")
    op.drop_column("credential_refs", "current_secret_version_id")
