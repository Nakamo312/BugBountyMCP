"""create arjun_candidate_endpoints and update host_endpoint_stats views

Revision ID: 7a8b9c1d2e3f
Revises: 216630f036d6
Create Date: 2026-01-04 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7a8b9c1d2e3f'
down_revision: Union[str, None] = '216630f036d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create arjun_candidate_endpoints and update host_endpoint_stats views"""

    # Create arjun_candidate_endpoints view
    op.execute("""
        CREATE OR REPLACE VIEW arjun_candidate_endpoints AS
        SELECT DISTINCT
            e.id as endpoint_id,
            CONCAT(s.scheme, '://', h.host, ':', s.port, e.path) as full_url,
            e.path,
            e.normalized_path,
            e.status_code,
            e.methods,
            h.host,
            h.program_id
        FROM endpoints e
        JOIN hosts h ON e.host_id = h.id
        JOIN services s ON e.service_id = s.id
        WHERE
            e.status_code IN (200, 201, 400, 403, 405)
            AND e.path NOT IN ('/', '/robots.txt', '/favicon.ico', '/sitemap.xml')
            AND e.path NOT LIKE '%.css'
            AND e.path NOT LIKE '%.js'
            AND e.path NOT LIKE '%.png'
            AND e.path NOT LIKE '%.jpg'
            AND e.path NOT LIKE '%.jpeg'
            AND e.path NOT LIKE '%.gif'
            AND e.path NOT LIKE '%.svg'
            AND e.path NOT LIKE '%.woff%'
            AND e.path NOT LIKE '%.ico'
            AND e.path NOT LIKE '%.docx'
            AND e.path NOT LIKE '%.pptx'
            AND e.path NOT LIKE '%.json'
            AND e.path NOT LIKE '%.txt'
            AND (
                e.normalized_path LIKE '%{id}%'
                OR e.normalized_path LIKE '%{sha256}%'
                OR e.status_code IN (200, 302, 400, 403, 405, 503)
            )
        ORDER BY e.status_code DESC;
    """)

    # Update host_endpoint_stats view
    op.execute("""
        CREATE OR REPLACE VIEW host_endpoint_stats AS
        SELECT
            h.host,
            h.program_id,
            i.address,
            count(DISTINCT e.id) AS count_endpoints,
            count(DISTINCT ip.id) AS count_input_parameters
        FROM (((hosts h
            RIGHT JOIN host_ips hi ON ((hi.host_id = h.id)))
            LEFT JOIN ip_addresses i ON ((i.id = hi.ip_id)))
            RIGHT JOIN endpoints e ON ((e.host_id = h.id)))
            LEFT JOIN input_parameters ip ON ((ip.endpoint_id = e.id))
        GROUP BY h.host, h.program_id, i.address
        ORDER BY (count(DISTINCT e.id)) DESC;
    """)


def downgrade() -> None:
    """Drop arjun_candidate_endpoints and revert host_endpoint_stats view"""

    # Drop arjun_candidate_endpoints view
    op.execute("DROP VIEW IF EXISTS arjun_candidate_endpoints;")

    # Revert host_endpoint_stats view to original
    op.execute("""
        CREATE OR REPLACE VIEW host_endpoint_stats AS
        SELECT
            h.host,
            i.address,
            count(*) AS count_endpoints
        FROM (((hosts h
            RIGHT JOIN host_ips hi ON ((hi.host_id = h.id)))
            LEFT JOIN ip_addresses i ON ((i.id = hi.ip_id)))
            RIGHT JOIN endpoints e ON ((e.host_id = h.id)))
        GROUP BY h.host, i.address
        ORDER BY (count(*)) DESC;
    """)
