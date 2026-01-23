"""Add API views for host services, endpoints with body, and full endpoint details

Revision ID: a1b2c3d4e5f6
Revises: 216630f036d6
Create Date: 2026-01-23

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '216630f036d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE VIEW host_services_view AS
        SELECT
            h.id as host_id,
            h.host,
            h.program_id,
            h.in_scope,
            s.id as service_id,
            s.scheme,
            s.port,
            s.technologies,
            s.favicon_hash,
            s.websocket
        FROM hosts h
        JOIN host_ips hi ON hi.host_id = h.id
        JOIN services s ON s.ip_id = hi.ip_id;
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

    op.execute("""
        CREATE OR REPLACE VIEW endpoint_full_details AS
        SELECT
            e.id as endpoint_id,
            h.id as host_id,
            h.host,
            h.program_id,
            s.id as service_id,
            s.scheme,
            s.port,
            s.technologies,
            concat(s.scheme, '://', h.host,
                   CASE WHEN s.port IN (80, 443) THEN '' ELSE ':' || s.port END,
                   e.path) AS full_url,
            e.path,
            e.normalized_path,
            e.methods,
            e.status_code,
            count(DISTINCT ip.id) as param_count,
            count(DISTINCT hd.id) as header_count,
            count(DISTINCT rb.id) as body_count
        FROM endpoints e
        JOIN hosts h ON e.host_id = h.id
        JOIN services s ON e.service_id = s.id
        LEFT JOIN input_parameters ip ON ip.endpoint_id = e.id
        LEFT JOIN headers hd ON hd.endpoint_id = e.id
        LEFT JOIN raw_body rb ON rb.endpoint_id = e.id
        GROUP BY e.id, h.id, h.host, h.program_id, s.id, s.scheme, s.port,
                 s.technologies, e.path, e.normalized_path, e.methods, e.status_code;
    """)

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

    op.execute("""
        CREATE OR REPLACE VIEW program_stats AS
        SELECT
            p.id as program_id,
            p.name as program_name,
            count(DISTINCT h.id) as host_count,
            count(DISTINCT h.id) FILTER (WHERE h.in_scope = true) as in_scope_host_count,
            count(DISTINCT e.id) as endpoint_count,
            count(DISTINCT ip.id) as parameter_count,
            count(DISTINCT s.id) as service_count,
            count(DISTINCT ia.id) as ip_count
        FROM programs p
        LEFT JOIN hosts h ON h.program_id = p.id
        LEFT JOIN endpoints e ON e.host_id = h.id
        LEFT JOIN input_parameters ip ON ip.endpoint_id = e.id
        LEFT JOIN host_ips hi ON hi.host_id = h.id
        LEFT JOIN services s ON s.ip_id = hi.ip_id
        LEFT JOIN ip_addresses ia ON ia.id = hi.ip_id
        GROUP BY p.id, p.name;
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS program_stats;")
    op.execute("DROP VIEW IF EXISTS host_full_stats;")
    op.execute("DROP VIEW IF EXISTS endpoint_full_details;")
    op.execute("DROP VIEW IF EXISTS endpoints_with_body;")
    op.execute("DROP VIEW IF EXISTS host_services_view;")
