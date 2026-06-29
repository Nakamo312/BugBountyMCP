"""Project action outcome memory into graph events.

Revision ID: m9n0o1p2q3r4
Revises: l8m9n0o1p2q3
"""

from alembic import op


revision = "m9n0o1p2q3r4"
down_revision = "l8m9n0o1p2q3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
CREATE OR REPLACE FUNCTION deterministic_uuid_from_text(value text)
RETURNS uuid
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    digest text;
BEGIN
    digest := md5(value);
    RETURN (
        substr(digest, 1, 8) || '-' ||
        substr(digest, 9, 4) || '-' ||
        substr(digest, 13, 4) || '-' ||
        substr(digest, 17, 4) || '-' ||
        substr(digest, 21, 12)
    )::uuid;
END
$$;
        """
    )
    op.execute(
        """
CREATE OR REPLACE FUNCTION enqueue_action_outcome_graph_projection_event()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    projection_dedupe_key text;
    projection_event_id uuid;
    projection_revision text;
    projection_event_type text;
BEGIN
    projection_revision := to_char(coalesce(NEW.updated_at, now()) AT TIME ZONE 'UTC', 'YYYYMMDDHH24MISSUS');
    IF TG_OP = 'INSERT' THEN
        projection_event_type := 'action_outcome_recorded';
    ELSE
        projection_event_type := 'action_outcome_updated';
    END IF;

    projection_dedupe_key := projection_event_type || ':' || NEW.id::text || ':' || projection_revision;
    projection_event_id := deterministic_uuid_from_text(projection_dedupe_key);

    INSERT INTO graph_projection_events (
        id,
        program_id,
        source_type,
        source_id,
        event_type,
        dedupe_key
    )
    VALUES (
        projection_event_id,
        NEW.program_id,
        'action_outcome',
        NEW.id,
        projection_event_type,
        projection_dedupe_key
    )
    ON CONFLICT (dedupe_key) DO NOTHING;

    PERFORM pg_notify('graph_projection_events_changed', projection_dedupe_key);
    RETURN NEW;
END
$$;
        """
    )
    op.execute(
        """
CREATE TRIGGER action_outcomes_graph_projection_event_insert
AFTER INSERT ON action_outcomes
FOR EACH ROW
EXECUTE FUNCTION enqueue_action_outcome_graph_projection_event();
        """
    )
    op.execute(
        """
CREATE TRIGGER action_outcomes_graph_projection_event_update
AFTER UPDATE OF
    status,
    terminal_outcome,
    finished_at,
    duration_ms,
    error_count,
    raw_artifact_count,
    raw_artifact_bytes,
    observed_hosts_count,
    observed_services_count,
    observed_endpoints_count,
    http_observation_count,
    javascript_reference_count,
    information_gain_score,
    manual_interest,
    manual_stop,
    continued_by_followup,
    report_created,
    triage_outcome,
    updated_at
ON action_outcomes
FOR EACH ROW
WHEN (OLD IS DISTINCT FROM NEW)
EXECUTE FUNCTION enqueue_action_outcome_graph_projection_event();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS action_outcomes_graph_projection_event_update ON action_outcomes;")
    op.execute("DROP TRIGGER IF EXISTS action_outcomes_graph_projection_event_insert ON action_outcomes;")
    op.execute("DROP FUNCTION IF EXISTS enqueue_action_outcome_graph_projection_event();")
    op.execute("DROP FUNCTION IF EXISTS deterministic_uuid_from_text(text);")
