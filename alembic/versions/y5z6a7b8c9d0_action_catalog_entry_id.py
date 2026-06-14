"""Add action catalog entry reference.

Revision ID: y5z6a7b8c9d0
Revises: x4y5z6a7b8c9
Create Date: 2026-06-12 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "y5z6a7b8c9d0"
down_revision = "x4y5z6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "action_requests",
        sa.Column("catalog_entry_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_action_requests_catalog_entry_id",
        "action_requests",
        "tool_catalog_entries",
        ["catalog_entry_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_action_requests_catalog_entry_id",
        "action_requests",
        ["catalog_entry_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_action_requests_catalog_entry_id", table_name="action_requests")
    op.drop_constraint(
        "fk_action_requests_catalog_entry_id",
        "action_requests",
        type_="foreignkey",
    )
    op.drop_column("action_requests", "catalog_entry_id")
