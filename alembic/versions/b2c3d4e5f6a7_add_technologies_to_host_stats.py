"""Add technologies to host_full_stats view

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-01-24

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE VIEW host_full_stats AS
        SELECT
            h.id as host_id,
            h.host,
            h.program_id,
            h.in_scope,
            h.cname,
            count(DISTINCT e.id) as endpoint_count,
            count(DISTINCT ip.id) as parameter_count,
            count(DISTINCT rb.id) as body_count,
            count(DISTINCT hd.id) as header_count,
            array_agg(DISTINCT s.scheme || ':' || s.port) FILTER (WHERE s.id IS NOT NULL) as services,
            array_agg(DISTINCT unnested_method) FILTER (WHERE unnested_method IS NOT NULL) as all_methods,
            (
                SELECT jsonb_object_agg(key, value)
                FROM (
                    SELECT DISTINCT ON (key) key, value
                    FROM host_ips hi2
                    JOIN services s2 ON s2.ip_id = hi2.ip_id
                    CROSS JOIN LATERAL jsonb_each(COALESCE(s2.technologies, '{}'::jsonb)) AS t(key, value)
                    WHERE hi2.host_id = h.id
                ) sub
            ) as technologies
        FROM hosts h
        LEFT JOIN endpoints e ON e.host_id = h.id
        LEFT JOIN input_parameters ip ON ip.endpoint_id = e.id
        LEFT JOIN raw_body rb ON rb.endpoint_id = e.id
        LEFT JOIN headers hd ON hd.endpoint_id = e.id
        LEFT JOIN host_ips hi ON hi.host_id = h.id
        LEFT JOIN services s ON s.ip_id = hi.ip_id
        LEFT JOIN LATERAL unnest(e.methods) AS unnested_method ON true
        GROUP BY h.id, h.host, h.program_id, h.in_scope, h.cname;
    """)


def downgrade() -> None:
    op.execute("""
        CREATE OR REPLACE VIEW host_full_stats AS
        SELECT
            h.id as host_id,
            h.host,
            h.program_id,
            h.in_scope,
            h.cname,
            count(DISTINCT e.id) as endpoint_count,
            count(DISTINCT ip.id) as parameter_count,
            count(DISTINCT rb.id) as body_count,
            count(DISTINCT hd.id) as header_count,
            array_agg(DISTINCT s.scheme || ':' || s.port) FILTER (WHERE s.id IS NOT NULL) as services,
            array_agg(DISTINCT unnested_method) FILTER (WHERE unnested_method IS NOT NULL) as all_methods
        FROM hosts h
        LEFT JOIN endpoints e ON e.host_id = h.id
        LEFT JOIN input_parameters ip ON ip.endpoint_id = e.id
        LEFT JOIN raw_body rb ON rb.endpoint_id = e.id
        LEFT JOIN headers hd ON hd.endpoint_id = e.id
        LEFT JOIN host_ips hi ON hi.host_id = h.id
        LEFT JOIN services s ON s.ip_id = hi.ip_id
        LEFT JOIN LATERAL unnest(e.methods) AS unnested_method ON true
        GROUP BY h.id, h.host, h.program_id, h.in_scope, h.cname;
    """)
