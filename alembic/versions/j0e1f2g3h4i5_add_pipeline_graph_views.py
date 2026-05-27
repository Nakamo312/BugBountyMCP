"""Add pipeline graph views for Grafana Node graph

Revision ID: j0e1f2g3h4i5
Revises: i9d0e1f2g3h4
Create Date: 2026-05-27

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'j0e1f2g3h4i5'
down_revision: Union[str, None] = 'i9d0e1f2g3h4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP VIEW IF EXISTS pipeline_graph_edges;")
    op.execute("DROP VIEW IF EXISTS pipeline_graph_nodes;")
    op.execute("DROP TYPE IF EXISTS pipeline_graph_edges CASCADE;")
    op.execute("DROP TYPE IF EXISTS pipeline_graph_nodes CASCADE;")

    op.execute("""
        CREATE OR REPLACE VIEW pipeline_graph_nodes AS
        SELECT
            ('action:' || ar.id::text) AS id,
            ('Action ' || left(ar.id::text, 8)) AS title,
            ar.profile_id AS subtitle,
            ar.status AS mainstat,
            ar.capability_id AS secondarystat,
            'action' AS node_type,
            ar.status AS status,
            ar.created_at
        FROM action_requests ar

        UNION ALL

        SELECT
            ('job:' || j.id::text) AS id,
            ('Job ' || left(j.id::text, 8)) AS title,
            j.profile_id AS subtitle,
            j.status AS mainstat,
            j.capability_id AS secondarystat,
            'job' AS node_type,
            j.status AS status,
            j.created_at
        FROM jobs j

        UNION ALL

        SELECT
            ('run:' || r.id::text) AS id,
            COALESCE(r.node_id, 'Run ' || left(r.id::text, 8)) AS title,
            COALESCE(r.event_name, 'unknown event') AS subtitle,
            r.status AS mainstat,
            ('artifacts ' || count(DISTINCT ra.id)::text) AS secondarystat,
            'run' AS node_type,
            r.status AS status,
            r.created_at
        FROM runs r
        LEFT JOIN raw_artifacts ra ON ra.run_id = r.id
        GROUP BY r.id, r.node_id, r.event_name, r.status, r.created_at

        UNION ALL

        SELECT
            ('event:' || es.event_id::text) AS id,
            es.event_type AS title,
            es.source AS subtitle,
            ('confidence ' || round(es.confidence::numeric, 2)::text) AS mainstat,
            left(es.correlation_id::text, 8) AS secondarystat,
            'event' AS node_type,
            NULL::text AS status,
            es.created_at
        FROM event_store es

        UNION ALL

        SELECT
            ('artifact:' || ra.id::text) AS id,
            ra.artifact_type AS title,
            ra.node_id AS subtitle,
            pg_size_pretty(ra.size_bytes::bigint) AS mainstat,
            left(ra.sha256, 12) AS secondarystat,
            'artifact' AS node_type,
            NULL::text AS status,
            ra.created_at
        FROM raw_artifacts ra;
    """)

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


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS pipeline_graph_edges;")
    op.execute("DROP VIEW IF EXISTS pipeline_graph_nodes;")
