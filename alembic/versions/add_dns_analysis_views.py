"""add dns analysis views

Revision ID: add_dns_analysis_views
Revises: 9c0d1e2f3a4b
Create Date: 2026-01-04 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_dns_analysis_views'
down_revision: Union[str, None] = '9c0d1e2f3a4b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Subdomain Takeover Detection
    op.execute("""
        CREATE OR REPLACE VIEW v_subdomain_takeover_candidates AS
        SELECT
            p.name as program_name,
            h.host,
            dr.record_type,
            dr.value as cname_target,
            dr.is_wildcard
        FROM dns_records dr
        JOIN hosts h ON dr.host_id = h.id
        JOIN programs p ON h.program_id = p.id
        WHERE dr.record_type = 'CNAME'
        AND NOT EXISTS (
            SELECT 1 FROM dns_records dr2
            WHERE dr2.host_id = dr.host_id
            AND dr2.record_type = 'A'
        )
        ORDER BY h.host;
    """)

    # Email Security Analysis
    op.execute("""
        CREATE OR REPLACE VIEW v_email_security_analysis AS
        SELECT
            p.name as program_name,
            h.host as domain,
            EXISTS(SELECT 1 FROM dns_records WHERE host_id = h.id AND record_type = 'MX') as has_mx,
            EXISTS(SELECT 1 FROM dns_records WHERE host_id = h.id AND record_type = 'TXT' AND value LIKE '%v=spf1%') as has_spf,
            EXISTS(SELECT 1 FROM dns_records WHERE host_id = h.id AND record_type = 'TXT' AND value LIKE '%v=DMARC1%') as has_dmarc,
            (SELECT COUNT(*) FROM dns_records WHERE host_id = h.id AND record_type = 'MX') as mx_count
        FROM hosts h
        JOIN programs p ON h.program_id = p.id
        WHERE EXISTS (SELECT 1 FROM dns_records WHERE host_id = h.id)
        ORDER BY h.host;
    """)

    # Infrastructure Mapping
    op.execute("""
        CREATE OR REPLACE VIEW v_infrastructure_mapping AS
        SELECT
            p.name as program_name,
            dr.value as nameserver,
            COUNT(DISTINCT h.id) as domains_count,
            json_agg(DISTINCT h.host ORDER BY h.host) as domains
        FROM dns_records dr
        JOIN hosts h ON dr.host_id = h.id
        JOIN programs p ON h.program_id = p.id
        WHERE dr.record_type = 'NS'
        GROUP BY p.name, dr.value
        ORDER BY domains_count DESC;
    """)

    # DNS Record Summary by Program
    op.execute("""
        CREATE OR REPLACE VIEW v_dns_summary_by_program AS
        SELECT
            p.name as program_name,
            COUNT(DISTINCT h.id) as hosts_with_dns,
            COUNT(CASE WHEN dr.record_type = 'A' THEN 1 END) as a_records,
            COUNT(CASE WHEN dr.record_type = 'AAAA' THEN 1 END) as aaaa_records,
            COUNT(CASE WHEN dr.record_type = 'CNAME' THEN 1 END) as cname_records,
            COUNT(CASE WHEN dr.record_type = 'MX' THEN 1 END) as mx_records,
            COUNT(CASE WHEN dr.record_type = 'TXT' THEN 1 END) as txt_records,
            COUNT(CASE WHEN dr.record_type = 'NS' THEN 1 END) as ns_records,
            COUNT(CASE WHEN dr.record_type = 'SOA' THEN 1 END) as soa_records,
            COUNT(CASE WHEN dr.is_wildcard = true THEN 1 END) as wildcard_count
        FROM dns_records dr
        JOIN hosts h ON dr.host_id = h.id
        JOIN programs p ON h.program_id = p.id
        GROUP BY p.name
        ORDER BY hosts_with_dns DESC;
    """)

    # Wildcard DNS Detection
    op.execute("""
        CREATE OR REPLACE VIEW v_wildcard_dns AS
        SELECT
            p.name as program_name,
            h.host,
            dr.record_type,
            dr.value
        FROM dns_records dr
        JOIN hosts h ON dr.host_id = h.id
        JOIN programs p ON h.program_id = p.id
        WHERE dr.is_wildcard = true
        ORDER BY h.host;
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_subdomain_takeover_candidates;")
    op.execute("DROP VIEW IF EXISTS v_email_security_analysis;")
    op.execute("DROP VIEW IF EXISTS v_infrastructure_mapping;")
    op.execute("DROP VIEW IF EXISTS v_dns_summary_by_program;")
    op.execute("DROP VIEW IF EXISTS v_wildcard_dns;")
