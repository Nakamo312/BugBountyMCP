"""Guard pipeline graph edges against missing nodes

Revision ID: l2g3h4i5j6k7
Revises: k1f2g3h4i5j6
Create Date: 2026-05-27

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'l2g3h4i5j6k7'
down_revision: Union[str, None] = 'k1f2g3h4i5j6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE VIEW pipeline_graph_edges AS
        SELECT
            ('action-job:' || ar.id::text || ':' || j.id::text) AS id,
            ('action:' || ar.id::text) AS source,
            ('job:' || j.id::text) AS target,
            'creates' AS mainstat,
            j.status AS secondarystat,
            'action_job' AS edge_type,
            j.created_at
        FROM action_requests ar
        JOIN jobs j ON j.action_id = ar.id

        UNION ALL

        SELECT
            ('job-run:' || j.id::text || ':' || r.id::text) AS id,
            ('job:' || j.id::text) AS source,
            ('run:' || r.id::text) AS target,
            'runs' AS mainstat,
            r.status AS secondarystat,
            'job_run' AS edge_type,
            r.created_at
        FROM runs r
        JOIN jobs j ON j.id = r.job_id

        UNION ALL

        SELECT
            ('run-event:' || r.id::text || ':' || es.event_id::text) AS id,
            ('run:' || r.id::text) AS source,
            ('event:' || es.event_id::text) AS target,
            'records' AS mainstat,
            es.event_type AS secondarystat,
            'run_event' AS edge_type,
            es.created_at
        FROM event_store es
        JOIN runs r ON r.id = es.run_id

        UNION ALL

        SELECT
            ('event-causation:' || parent.event_id::text || ':' || child.event_id::text) AS id,
            ('event:' || parent.event_id::text) AS source,
            ('event:' || child.event_id::text) AS target,
            'causes' AS mainstat,
            child.event_type AS secondarystat,
            'event_causation' AS edge_type,
            child.created_at
        FROM event_store child
        JOIN event_store parent ON parent.event_id = child.causation_id

        UNION ALL

        SELECT
            ('run-artifact:' || r.id::text || ':' || ra.id::text) AS id,
            ('run:' || r.id::text) AS source,
            ('artifact:' || ra.id::text) AS target,
            'writes' AS mainstat,
            pg_size_pretty(ra.size_bytes::bigint) AS secondarystat,
            'run_artifact' AS edge_type,
            ra.created_at
        FROM raw_artifacts ra
        JOIN runs r ON r.id = ra.run_id;
    """)


def downgrade() -> None:
    op.execute("""
        CREATE OR REPLACE VIEW pipeline_graph_edges AS
        SELECT
            ('action-job:' || ar.id::text || ':' || j.id::text) AS id,
            ('action:' || ar.id::text) AS source,
            ('job:' || j.id::text) AS target,
            'creates' AS mainstat,
            j.status AS secondarystat,
            'action_job' AS edge_type,
            j.created_at
        FROM action_requests ar
        JOIN jobs j ON j.action_id = ar.id

        UNION ALL

        SELECT
            ('job-run:' || r.job_id::text || ':' || r.id::text) AS id,
            ('job:' || r.job_id::text) AS source,
            ('run:' || r.id::text) AS target,
            'runs' AS mainstat,
            r.status AS secondarystat,
            'job_run' AS edge_type,
            r.created_at
        FROM runs r

        UNION ALL

        SELECT
            ('run-event:' || es.run_id::text || ':' || es.event_id::text) AS id,
            ('run:' || es.run_id::text) AS source,
            ('event:' || es.event_id::text) AS target,
            'records' AS mainstat,
            es.event_type AS secondarystat,
            'run_event' AS edge_type,
            es.created_at
        FROM event_store es
        WHERE es.run_id IS NOT NULL

        UNION ALL

        SELECT
            ('event-causation:' || es.causation_id::text || ':' || es.event_id::text) AS id,
            ('event:' || es.causation_id::text) AS source,
            ('event:' || es.event_id::text) AS target,
            'causes' AS mainstat,
            es.event_type AS secondarystat,
            'event_causation' AS edge_type,
            es.created_at
        FROM event_store es
        WHERE es.causation_id IS NOT NULL

        UNION ALL

        SELECT
            ('run-artifact:' || ra.run_id::text || ':' || ra.id::text) AS id,
            ('run:' || ra.run_id::text) AS source,
            ('artifact:' || ra.id::text) AS target,
            'writes' AS mainstat,
            pg_size_pretty(ra.size_bytes::bigint) AS secondarystat,
            'run_artifact' AS edge_type,
            ra.created_at
        FROM raw_artifacts ra
        WHERE ra.run_id IS NOT NULL;
    """)
