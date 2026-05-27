"""Add pipeline overview views for Grafana

Revision ID: i9d0e1f2g3h4
Revises: h8c9d0e1f2g3
Create Date: 2026-05-27

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'i9d0e1f2g3h4'
down_revision: Union[str, None] = 'h8c9d0e1f2g3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE VIEW pipeline_action_overview AS
        SELECT
            ar.id AS action_id,
            ar.program_id,
            ar.kind,
            ar.capability_id,
            ar.profile_id,
            ar.requested_by,
            ar.status AS action_status,
            pd.status AS policy_status,
            pd.reasons AS policy_reasons,
            pd.allowed_targets,
            pd.blocked_targets,
            j.id AS job_id,
            j.status AS job_status,
            j.correlation_id,
            ar.created_at AS requested_at,
            ar.updated_at AS action_updated_at,
            j.created_at AS job_created_at,
            j.updated_at AS job_updated_at
        FROM action_requests ar
        LEFT JOIN LATERAL (
            SELECT
                status,
                reasons,
                allowed_targets,
                blocked_targets
            FROM policy_decisions pd
            WHERE pd.action_id = ar.id
            ORDER BY pd.created_at DESC
            LIMIT 1
        ) pd ON true
        LEFT JOIN jobs j ON j.action_id = ar.id;
    """)

    op.execute("""
        CREATE OR REPLACE VIEW pipeline_run_overview AS
        SELECT
            r.id AS run_id,
            r.job_id,
            r.program_id,
            j.action_id,
            j.capability_id,
            j.profile_id,
            j.correlation_id,
            r.node_id,
            r.event_name,
            r.trigger_event_id,
            r.status AS run_status,
            r.attempt,
            r.started_at,
            r.finished_at,
            r.created_at,
            r.updated_at,
            r.error,
            EXTRACT(EPOCH FROM (COALESCE(r.finished_at, now()) - COALESCE(r.started_at, r.created_at)))::bigint
                AS age_seconds,
            COUNT(DISTINCT es.event_id) AS event_count,
            COUNT(DISTINCT ra.id) AS artifact_count
        FROM runs r
        JOIN jobs j ON j.id = r.job_id
        LEFT JOIN event_store es ON es.run_id = r.id
        LEFT JOIN raw_artifacts ra ON ra.run_id = r.id
        GROUP BY
            r.id,
            r.job_id,
            r.program_id,
            j.action_id,
            j.capability_id,
            j.profile_id,
            j.correlation_id,
            r.node_id,
            r.event_name,
            r.trigger_event_id,
            r.status,
            r.attempt,
            r.started_at,
            r.finished_at,
            r.created_at,
            r.updated_at,
            r.error;
    """)

    op.execute("""
        CREATE OR REPLACE VIEW pipeline_artifact_overview AS
        SELECT
            ra.id AS artifact_id,
            ra.program_id,
            ra.job_id,
            ra.run_id,
            j.action_id,
            j.correlation_id,
            ra.node_id,
            ra.event_name,
            ra.artifact_type,
            ra.storage_uri,
            ra.sha256,
            ra.size_bytes,
            ra.created_at
        FROM raw_artifacts ra
        LEFT JOIN jobs j ON j.id = ra.job_id;
    """)

    op.execute("""
        CREATE OR REPLACE VIEW pipeline_event_timeline AS
        SELECT
            es.event_id,
            es.event_type,
            es.program_id,
            es.job_id,
            es.run_id,
            es.correlation_id,
            es.causation_id,
            es.source,
            es.profile,
            es.confidence,
            r.node_id,
            r.status AS run_status,
            es.created_at
        FROM event_store es
        LEFT JOIN runs r ON r.id = es.run_id;
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS pipeline_event_timeline;")
    op.execute("DROP VIEW IF EXISTS pipeline_artifact_overview;")
    op.execute("DROP VIEW IF EXISTS pipeline_run_overview;")
    op.execute("DROP VIEW IF EXISTS pipeline_action_overview;")
