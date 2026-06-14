"""Use event_store as transactional dispatch log.

Revision ID: x4y5z6a7b8c9
Revises: w3x4y5z6a7b8
Create Date: 2026-06-11 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "x4y5z6a7b8c9"
down_revision: Union[str, None] = "w3x4y5z6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "event_dispatches",
        sa.Column("id", UUID, nullable=False),
        sa.Column("event_id", UUID, nullable=False),
        sa.Column("destination", sa.String(length=100), nullable=False),
        sa.Column("routing_key", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("locked_by", sa.String(length=100), nullable=True),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("destination != ''", name="ck_event_dispatches_destination_not_empty"),
        sa.CheckConstraint("routing_key != ''", name="ck_event_dispatches_routing_key_not_empty"),
        sa.CheckConstraint("attempts >= 0", name="ck_event_dispatches_attempts_nonnegative"),
        sa.CheckConstraint(
            "status IN ('pending', 'locked', 'dispatched', 'failed', 'dead')",
            name="ck_event_dispatches_status_valid",
        ),
        sa.ForeignKeyConstraint(["event_id"], ["event_store.event_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "destination", name="uq_event_dispatches_event_destination"),
    )
    op.create_index("ix_event_dispatches_event_id", "event_dispatches", ["event_id"])
    op.create_index("ix_event_dispatches_destination", "event_dispatches", ["destination"])
    op.create_index("ix_event_dispatches_status", "event_dispatches", ["status"])
    op.create_index("ix_event_dispatches_available_at", "event_dispatches", ["available_at"])
    op.create_index(
        "idx_event_dispatches_status_available",
        "event_dispatches",
        ["status", "available_at"],
    )
    op.create_index(
        "idx_event_dispatches_destination_status",
        "event_dispatches",
        ["destination", "status"],
    )


def downgrade() -> None:
    op.drop_index("idx_event_dispatches_destination_status", table_name="event_dispatches")
    op.drop_index("idx_event_dispatches_status_available", table_name="event_dispatches")
    op.drop_index("ix_event_dispatches_available_at", table_name="event_dispatches")
    op.drop_index("ix_event_dispatches_status", table_name="event_dispatches")
    op.drop_index("ix_event_dispatches_destination", table_name="event_dispatches")
    op.drop_index("ix_event_dispatches_event_id", table_name="event_dispatches")
    op.drop_table("event_dispatches")
