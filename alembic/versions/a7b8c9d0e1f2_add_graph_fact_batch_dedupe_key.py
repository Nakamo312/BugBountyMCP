"""Add idempotent GraphFactBatch dedupe key.

Revision ID: a7b8c9d0e1f2
Revises: z6a7b8c9d0e1
Create Date: 2026-06-13 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "a7b8c9d0e1f2"
down_revision = "z6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("graph_fact_batches", sa.Column("dedupe_key", sa.String(length=300), nullable=True))
    op.create_check_constraint(
        "ck_graph_fact_batches_dedupe_key_not_empty",
        "graph_fact_batches",
        "dedupe_key IS NULL OR dedupe_key != ''",
    )
    op.create_index(
        "uq_graph_fact_batches_dedupe_key",
        "graph_fact_batches",
        ["dedupe_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_graph_fact_batches_dedupe_key", table_name="graph_fact_batches")
    op.drop_constraint("ck_graph_fact_batches_dedupe_key_not_empty", "graph_fact_batches", type_="check")
    op.drop_column("graph_fact_batches", "dedupe_key")
