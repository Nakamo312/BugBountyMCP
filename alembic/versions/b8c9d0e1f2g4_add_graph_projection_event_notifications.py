"""Add graph projection event notifications.

Revision ID: b8c9d0e1f2g4
Revises: a7b8c9d0e1f3
Create Date: 2026-06-17
"""
from __future__ import annotations

from alembic import op


revision = "b8c9d0e1f2g4"
down_revision = "a7b8c9d0e1f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
CREATE OR REPLACE FUNCTION notify_graph_projection_event_changed()
RETURNS trigger AS $$
BEGIN
    IF NEW.status IN ('pending', 'failed') THEN
        PERFORM pg_notify('graph_projection_events_changed', NEW.dedupe_key);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
""".strip()
    )
    op.execute(
        """
CREATE TRIGGER graph_projection_events_notify_insert
AFTER INSERT ON graph_projection_events
FOR EACH ROW
EXECUTE FUNCTION notify_graph_projection_event_changed();
""".strip()
    )
    op.execute(
        """
CREATE TRIGGER graph_projection_events_notify_status
AFTER UPDATE OF status, available_at ON graph_projection_events
FOR EACH ROW
WHEN (OLD.status IS DISTINCT FROM NEW.status OR OLD.available_at IS DISTINCT FROM NEW.available_at)
EXECUTE FUNCTION notify_graph_projection_event_changed();
""".strip()
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS graph_projection_events_notify_status ON graph_projection_events;")
    op.execute("DROP TRIGGER IF EXISTS graph_projection_events_notify_insert ON graph_projection_events;")
    op.execute("DROP FUNCTION IF EXISTS notify_graph_projection_event_changed();")
