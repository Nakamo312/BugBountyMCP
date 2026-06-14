"""Materialize manifest-first tool catalog snapshots.

Revision ID: v2w3x4y5z6a7
Revises: u1v2w3x4y5z6
Create Date: 2026-06-11 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "v2w3x4y5z6a7"
down_revision: Union[str, None] = "u1v2w3x4y5z6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


JSONB = postgresql.JSONB(astext_type=sa.Text())
UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "tool_catalog_snapshots",
        sa.Column("id", UUID, nullable=False),
        sa.Column("catalog_hash", sa.String(length=64), nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=True),
        sa.Column("schema_version", sa.String(length=50), nullable=False),
        sa.Column("manifest_json", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("catalog_hash != ''", name="ck_tool_catalog_snapshots_hash_not_empty"),
        sa.CheckConstraint("source_hash != ''", name="ck_tool_catalog_snapshots_source_hash_not_empty"),
        sa.CheckConstraint("schema_version != ''", name="ck_tool_catalog_snapshots_schema_not_empty"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("catalog_hash", name="uq_tool_catalog_snapshots_hash"),
    )
    op.create_index("ix_tool_catalog_snapshots_catalog_hash", "tool_catalog_snapshots", ["catalog_hash"])
    op.create_index("ix_tool_catalog_snapshots_source_hash", "tool_catalog_snapshots", ["source_hash"])

    op.create_table(
        "tool_catalog_entries",
        sa.Column("id", UUID, nullable=False),
        sa.Column("snapshot_id", UUID, nullable=False),
        sa.Column("capability_id", sa.String(length=100), nullable=False),
        sa.Column("profile_id", sa.String(length=100), nullable=False),
        sa.Column("capability_label", sa.String(length=255), nullable=False),
        sa.Column("profile_label", sa.String(length=255), nullable=False),
        sa.Column("request_event", sa.String(length=150), nullable=False),
        sa.Column("queue", sa.String(length=100), nullable=False),
        sa.Column("default_profile", sa.String(length=100), nullable=False),
        sa.Column("mode", sa.String(length=50), nullable=False),
        sa.Column("scope_policy", sa.String(length=50), nullable=False),
        sa.Column("safety_class", sa.String(length=50), nullable=False),
        sa.Column("allowed_options", JSONB, nullable=False),
        sa.Column("requires_approval", sa.Boolean(), nullable=False),
        sa.Column("frontend", JSONB, nullable=False),
        sa.Column("manifest_fragment", JSONB, nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("capability_id != ''", name="ck_tool_catalog_entries_capability_not_empty"),
        sa.CheckConstraint("profile_id != ''", name="ck_tool_catalog_entries_profile_not_empty"),
        sa.CheckConstraint("request_event != ''", name="ck_tool_catalog_entries_event_not_empty"),
        sa.CheckConstraint("queue != ''", name="ck_tool_catalog_entries_queue_not_empty"),
        sa.CheckConstraint("safety_class IN ('passive', 'safe_active', 'active', 'sensitive')", name="ck_tool_catalog_entries_safety_valid"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["tool_catalog_snapshots.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("snapshot_id", "capability_id", "profile_id", name="uq_tool_catalog_entries_snapshot_profile"),
    )
    op.create_index("ix_tool_catalog_entries_snapshot_id", "tool_catalog_entries", ["snapshot_id"])
    op.create_index("ix_tool_catalog_entries_capability_id", "tool_catalog_entries", ["capability_id"])
    op.create_index("ix_tool_catalog_entries_profile_id", "tool_catalog_entries", ["profile_id"])
    op.create_index("ix_tool_catalog_entries_request_event", "tool_catalog_entries", ["request_event"])
    op.create_index("ix_tool_catalog_entries_safety_class", "tool_catalog_entries", ["safety_class"])
    op.create_index("ix_tool_catalog_entries_active", "tool_catalog_entries", ["active"])
    op.create_index("idx_tool_catalog_entries_active_capability", "tool_catalog_entries", ["active", "capability_id", "profile_id"])


def downgrade() -> None:
    op.drop_index("idx_tool_catalog_entries_active_capability", table_name="tool_catalog_entries")
    op.drop_index("ix_tool_catalog_entries_active", table_name="tool_catalog_entries")
    op.drop_index("ix_tool_catalog_entries_safety_class", table_name="tool_catalog_entries")
    op.drop_index("ix_tool_catalog_entries_request_event", table_name="tool_catalog_entries")
    op.drop_index("ix_tool_catalog_entries_profile_id", table_name="tool_catalog_entries")
    op.drop_index("ix_tool_catalog_entries_capability_id", table_name="tool_catalog_entries")
    op.drop_index("ix_tool_catalog_entries_snapshot_id", table_name="tool_catalog_entries")
    op.drop_table("tool_catalog_entries")
    op.drop_index("ix_tool_catalog_snapshots_source_hash", table_name="tool_catalog_snapshots")
    op.drop_index("ix_tool_catalog_snapshots_catalog_hash", table_name="tool_catalog_snapshots")
    op.drop_table("tool_catalog_snapshots")
