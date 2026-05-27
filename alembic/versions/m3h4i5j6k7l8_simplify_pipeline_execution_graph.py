"""Simplify pipeline graph to execution flow

Revision ID: m3h4i5j6k7l8
Revises: l2g3h4i5j6k7
Create Date: 2026-05-27

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'm3h4i5j6k7l8'
down_revision: Union[str, None] = 'l2g3h4i5j6k7'
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
            CASE
                WHEN r.error IS NOT NULL THEN left(r.error, 60)
                ELSE ('artifacts ' || count(DISTINCT ra.id)::text)
            END AS secondarystat,
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
        GROUP BY r.id, r.node_id, r.event_name, r.status, r.error, r.created_at

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
        FROM raw_artifacts ra
        JOIN runs r ON r.id = ra.run_id;
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
    op.execute("DROP VIEW IF EXISTS pipeline_graph_edges;")
    op.execute("DROP VIEW IF EXISTS pipeline_graph_nodes;")
