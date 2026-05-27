"""Add render fields for Grafana Node graph

Revision ID: k1f2g3h4i5j6
Revises: j0e1f2g3h4i5
Create Date: 2026-05-27

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'k1f2g3h4i5j6'
down_revision: Union[str, None] = 'j0e1f2g3h4i5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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
            ar.created_at,
            42::numeric AS "nodeRadius",
            CASE ar.status
                WHEN 'queued' THEN 'blue'
                WHEN 'blocked' THEN 'orange'
                WHEN 'requires_approval' THEN 'yellow'
                WHEN 'rejected' THEN 'red'
                ELSE 'gray'
            END AS color
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
            j.created_at,
            46::numeric AS "nodeRadius",
            CASE j.status
                WHEN 'queued' THEN 'blue'
                WHEN 'running' THEN 'green'
                WHEN 'completed' THEN 'green'
                WHEN 'failed' THEN 'red'
                WHEN 'cancelled' THEN 'orange'
                ELSE 'gray'
            END AS color
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
            r.created_at,
            52::numeric AS "nodeRadius",
            CASE r.status
                WHEN 'queued' THEN 'blue'
                WHEN 'running' THEN 'green'
                WHEN 'completed' THEN 'green'
                WHEN 'failed' THEN 'red'
                WHEN 'cancelled' THEN 'orange'
                ELSE 'gray'
            END AS color
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
            es.created_at,
            38::numeric AS "nodeRadius",
            'purple' AS color
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
            ra.created_at,
            34::numeric AS "nodeRadius",
            'gray' AS color
        FROM raw_artifacts ra;
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS pipeline_graph_nodes;")
    op.execute("""
        CREATE VIEW pipeline_graph_nodes AS
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
