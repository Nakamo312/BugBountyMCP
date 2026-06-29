"""Add durable OpenSearch projection event queue.

Revision ID: d7e8f9a0b1c2
Revises: c7d8e9f0a1b2
Create Date: 2026-06-27 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d7e8f9a0b1c2"
down_revision: Union[str, None] = "c7d8e9f0a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSONB = postgresql.JSONB(astext_type=sa.Text())
UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "search_projection_events",
        sa.Column("id", UUID, nullable=False),
        sa.Column("program_id", UUID, nullable=False),
        sa.Column("target", sa.String(length=120), nullable=False),
        sa.Column("source_type", sa.String(length=120), nullable=False),
        sa.Column("source_id", UUID, nullable=True),
        sa.Column("filters_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("dedupe_key", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("locked_by", sa.String(length=200), nullable=True),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("result_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("target != ''", name="ck_search_projection_events_target_not_empty"),
        sa.CheckConstraint("source_type != ''", name="ck_search_projection_events_source_type_not_empty"),
        sa.CheckConstraint("dedupe_key != ''", name="ck_search_projection_events_dedupe_not_empty"),
        sa.CheckConstraint("attempts >= 0", name="ck_search_projection_events_attempts_nonnegative"),
        sa.CheckConstraint(
            "status IN ('pending', 'locked', 'processed', 'failed', 'dead')",
            name="ck_search_projection_events_status_valid",
        ),
    )
    op.create_index("ix_search_projection_events_program_id", "search_projection_events", ["program_id"])
    op.create_index("ix_search_projection_events_target", "search_projection_events", ["target"])
    op.create_index("ix_search_projection_events_status", "search_projection_events", ["status"])
    op.create_index("ix_search_projection_events_available_at", "search_projection_events", ["available_at"])
    op.create_index(
        "idx_search_projection_events_status_available",
        "search_projection_events",
        ["status", "available_at"],
    )
    op.create_index(
        "uq_search_projection_events_dedupe_key",
        "search_projection_events",
        ["dedupe_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_search_projection_events_dedupe_key", table_name="search_projection_events")
    op.drop_index("idx_search_projection_events_status_available", table_name="search_projection_events")
    op.drop_index("ix_search_projection_events_available_at", table_name="search_projection_events")
    op.drop_index("ix_search_projection_events_status", table_name="search_projection_events")
    op.drop_index("ix_search_projection_events_target", table_name="search_projection_events")
    op.drop_index("ix_search_projection_events_program_id", table_name="search_projection_events")
    op.drop_table("search_projection_events")
