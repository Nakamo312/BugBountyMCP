"""Add graph fact batch projection notifications.

Revision ID: c9d0e1f2g3h4
Revises: b8c9d0e1f2g3
Create Date: 2026-06-13
"""
from __future__ import annotations

from alembic import op


revision = "c9d0e1f2g3h4"
down_revision = "b8c9d0e1f2g3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
CREATE OR REPLACE FUNCTION notify_graph_fact_batch_changed()
RETURNS trigger AS $$
BEGIN
    IF NEW.status IN ('pending', 'failed') THEN
        PERFORM pg_notify('graph_fact_batches_changed', NEW.id::text);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
""".strip()
    )
    op.execute(
        """
CREATE TRIGGER graph_fact_batches_notify_insert
AFTER INSERT ON graph_fact_batches
FOR EACH ROW
EXECUTE FUNCTION notify_graph_fact_batch_changed();
""".strip()
    )
    op.execute(
        """
CREATE TRIGGER graph_fact_batches_notify_status
AFTER UPDATE OF status, available_at ON graph_fact_batches
FOR EACH ROW
WHEN (OLD.status IS DISTINCT FROM NEW.status OR OLD.available_at IS DISTINCT FROM NEW.available_at)
EXECUTE FUNCTION notify_graph_fact_batch_changed();
""".strip()
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS graph_fact_batches_notify_status ON graph_fact_batches;")
    op.execute("DROP TRIGGER IF EXISTS graph_fact_batches_notify_insert ON graph_fact_batches;")
    op.execute("DROP FUNCTION IF EXISTS notify_graph_fact_batch_changed();")
