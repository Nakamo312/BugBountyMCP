"""Add credential registry, secret versions, and leases.

Revision ID: e8f9a0b1c2d3
Revises: d7e8f9a0b1c2
Create Date: 2026-06-28 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "e8f9a0b1c2d3"
down_revision: Union[str, None] = "d7e8f9a0b1c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSONB = postgresql.JSONB(astext_type=sa.Text())
UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "credential_refs",
        sa.Column("id", UUID, nullable=False),
        sa.Column("program_id", UUID, nullable=False),
        sa.Column("credential_ref", sa.String(length=255), nullable=False),
        sa.Column("identity_label", sa.String(length=150), nullable=False),
        sa.Column("secret_kind", sa.String(length=50), nullable=False),
        sa.Column("scope_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="active"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("program_id", "credential_ref", name="uq_credential_refs_program_ref"),
        sa.CheckConstraint("credential_ref LIKE 'credref:%'", name="ck_credential_refs_ref_prefix"),
        sa.CheckConstraint("identity_label != ''", name="ck_credential_refs_identity_not_empty"),
        sa.CheckConstraint("secret_kind != ''", name="ck_credential_refs_secret_kind_not_empty"),
        sa.CheckConstraint(
            "status IN ('active', 'disabled', 'revoked')",
            name="ck_credential_refs_status_valid",
        ),
    )
    op.create_index("ix_credential_refs_program_id", "credential_refs", ["program_id"])
    op.create_index("ix_credential_refs_status", "credential_refs", ["status"])
    op.create_index(
        "idx_credential_refs_program_identity",
        "credential_refs",
        ["program_id", "identity_label"],
    )
    op.create_index(
        "idx_credential_refs_program_status",
        "credential_refs",
        ["program_id", "status"],
    )

    op.create_table(
        "credential_secret_versions",
        sa.Column("id", UUID, nullable=False),
        sa.Column("credential_ref_id", UUID, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("secret_kind", sa.String(length=50), nullable=False),
        sa.Column("storage_backend", sa.String(length=80), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("nonce", sa.LargeBinary(), nullable=True),
        sa.Column("key_id", sa.String(length=120), nullable=True),
        sa.Column("external_secret_ref", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="active"),
        sa.Column("metadata_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["credential_ref_id"], ["credential_refs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("credential_ref_id", "version", name="uq_credential_secret_versions_ref_version"),
        sa.CheckConstraint("version > 0", name="ck_credential_secret_versions_version_positive"),
        sa.CheckConstraint("secret_kind != ''", name="ck_credential_secret_versions_kind_not_empty"),
        sa.CheckConstraint("storage_backend != ''", name="ck_credential_secret_versions_backend_not_empty"),
        sa.CheckConstraint(
            "status IN ('active', 'retired', 'revoked')",
            name="ck_credential_secret_versions_status_valid",
        ),
        sa.CheckConstraint(
            "ciphertext IS NOT NULL OR external_secret_ref IS NOT NULL",
            name="ck_credential_secret_versions_has_secret_pointer",
        ),
    )
    op.create_index(
        "ix_credential_secret_versions_credential_ref_id",
        "credential_secret_versions",
        ["credential_ref_id"],
    )
    op.create_index("ix_credential_secret_versions_status", "credential_secret_versions", ["status"])
    op.create_index(
        "idx_credential_secret_versions_ref_status",
        "credential_secret_versions",
        ["credential_ref_id", "status"],
    )

    op.create_table(
        "credential_leases",
        sa.Column("id", UUID, nullable=False),
        sa.Column("program_id", UUID, nullable=False),
        sa.Column("credential_ref_id", UUID, nullable=False),
        sa.Column("secret_version_id", UUID, nullable=False),
        sa.Column("purpose", sa.String(length=120), nullable=False),
        sa.Column("capability", sa.String(length=120), nullable=False),
        sa.Column("target_scope", sa.String(length=500), nullable=False),
        sa.Column("auth_injection_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="issued"),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("audit_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["credential_ref_id"], ["credential_refs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["secret_version_id"], ["credential_secret_versions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("purpose != ''", name="ck_credential_leases_purpose_not_empty"),
        sa.CheckConstraint("capability != ''", name="ck_credential_leases_capability_not_empty"),
        sa.CheckConstraint("target_scope != ''", name="ck_credential_leases_target_scope_not_empty"),
        sa.CheckConstraint(
            "status IN ('issued', 'used', 'expired', 'revoked')",
            name="ck_credential_leases_status_valid",
        ),
        sa.CheckConstraint("expires_at > issued_at", name="ck_credential_leases_expires_after_issued"),
    )
    op.create_index("ix_credential_leases_program_id", "credential_leases", ["program_id"])
    op.create_index("ix_credential_leases_credential_ref_id", "credential_leases", ["credential_ref_id"])
    op.create_index("ix_credential_leases_secret_version_id", "credential_leases", ["secret_version_id"])
    op.create_index("ix_credential_leases_status", "credential_leases", ["status"])
    op.create_index("ix_credential_leases_expires_at", "credential_leases", ["expires_at"])
    op.create_index(
        "idx_credential_leases_program_status_expires",
        "credential_leases",
        ["program_id", "status", "expires_at"],
    )
    op.create_index(
        "idx_credential_leases_ref_status",
        "credential_leases",
        ["credential_ref_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("idx_credential_leases_ref_status", table_name="credential_leases")
    op.drop_index("idx_credential_leases_program_status_expires", table_name="credential_leases")
    op.drop_index("ix_credential_leases_expires_at", table_name="credential_leases")
    op.drop_index("ix_credential_leases_status", table_name="credential_leases")
    op.drop_index("ix_credential_leases_secret_version_id", table_name="credential_leases")
    op.drop_index("ix_credential_leases_credential_ref_id", table_name="credential_leases")
    op.drop_index("ix_credential_leases_program_id", table_name="credential_leases")
    op.drop_table("credential_leases")

    op.drop_index("idx_credential_secret_versions_ref_status", table_name="credential_secret_versions")
    op.drop_index("ix_credential_secret_versions_status", table_name="credential_secret_versions")
    op.drop_index("ix_credential_secret_versions_credential_ref_id", table_name="credential_secret_versions")
    op.drop_table("credential_secret_versions")

    op.drop_index("idx_credential_refs_program_status", table_name="credential_refs")
    op.drop_index("idx_credential_refs_program_identity", table_name="credential_refs")
    op.drop_index("ix_credential_refs_status", table_name="credential_refs")
    op.drop_index("ix_credential_refs_program_id", table_name="credential_refs")
    op.drop_table("credential_refs")
