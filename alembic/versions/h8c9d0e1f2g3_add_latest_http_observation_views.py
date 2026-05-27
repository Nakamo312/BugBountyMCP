"""Add latest HTTP observation read views

Revision ID: h8c9d0e1f2g3
Revises: g7b8c9d0e1f2
Create Date: 2026-05-27

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'h8c9d0e1f2g3'
down_revision: Union[str, None] = 'g7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE VIEW latest_http_observations AS
        SELECT DISTINCT ON (endpoint_id)
            id AS observation_id,
            program_id,
            endpoint_id,
            service_id,
            job_id,
            run_id,
            correlation_id,
            raw_artifact_id,
            method,
            url,
            status_code,
            content_type,
            title,
            body_sha256,
            body_size_bytes,
            body_artifact_id,
            body_preview,
            source_tool,
            metadata,
            observed_at
        FROM http_observations
        ORDER BY endpoint_id, observed_at DESC, id DESC;
    """)

    op.execute("""
        CREATE OR REPLACE VIEW latest_http_observation_headers AS
        SELECT
            h.id,
            o.endpoint_id,
            h.observation_id,
            h.name,
            h.value,
            h.ordinal
        FROM latest_http_observations o
        JOIN http_observation_headers h ON h.observation_id = o.observation_id;
    """)

    op.execute("""
        CREATE OR REPLACE VIEW endpoints_with_body AS
        SELECT
            e.id as endpoint_id,
            h.id as host_id,
            h.host,
            h.program_id,
            concat(s.scheme, '://', h.host,
                   CASE WHEN s.port IN (80, 443) THEN '' ELSE ':' || s.port END,
                   e.path) AS full_url,
            e.path,
            e.normalized_path,
            e.methods,
            COALESCE(o.status_code, e.status_code) AS status_code,
            COALESCE(o.body_artifact_id, o.observation_id) AS raw_body_id,
            NULL::text AS body_content,
            o.body_sha256 AS body_hash,
            COALESCE(o.body_artifact_id::text, o.observation_id::text) AS body_ref,
            o.body_preview,
            o.body_size_bytes AS body_length
        FROM endpoints e
        JOIN hosts h ON e.host_id = h.id
        JOIN services s ON e.service_id = s.id
        LEFT JOIN latest_http_observations o ON o.endpoint_id = e.id
        WHERE 'POST' = ANY(e.methods)
           OR 'PUT' = ANY(e.methods)
           OR 'PATCH' = ANY(e.methods)
           OR o.body_sha256 IS NOT NULL
           OR o.body_artifact_id IS NOT NULL
           OR o.body_preview IS NOT NULL;
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS endpoints_with_body;")
    op.execute("DROP VIEW IF EXISTS latest_http_observation_headers;")
    op.execute("DROP VIEW IF EXISTS latest_http_observations;")

    op.execute("""
        CREATE OR REPLACE VIEW endpoints_with_body AS
        SELECT
            e.id as endpoint_id,
            h.id as host_id,
            h.host,
            h.program_id,
            concat(s.scheme, '://', h.host,
                   CASE WHEN s.port IN (80, 443) THEN '' ELSE ':' || s.port END,
                   e.path) AS full_url,
            e.path,
            e.normalized_path,
            e.methods,
            e.status_code,
            rb.id as raw_body_id,
            rb.body_content,
            rb.body_hash
        FROM endpoints e
        JOIN hosts h ON e.host_id = h.id
        JOIN services s ON e.service_id = s.id
        LEFT JOIN raw_body rb ON rb.endpoint_id = e.id
        WHERE 'POST' = ANY(e.methods)
           OR 'PUT' = ANY(e.methods)
           OR 'PATCH' = ANY(e.methods)
           OR rb.id IS NOT NULL;
    """)
