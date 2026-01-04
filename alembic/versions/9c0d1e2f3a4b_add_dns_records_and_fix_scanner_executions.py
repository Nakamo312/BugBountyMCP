"""add dns_records and fix scanner_executions program_id

Revision ID: 9c0d1e2f3a4b
Revises: 8b9c0d1e2f3a
Create Date: 2026-01-04 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = '9c0d1e2f3a4b'
down_revision: Union[str, None] = '8b9c0d1e2f3a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add dns_records table and fix scanner_executions.program_id"""

    # 1. Fix scanner_executions.program_id (String -> UUID with FK)
    op.execute("ALTER TABLE scanner_executions ALTER COLUMN program_id TYPE uuid USING program_id::uuid;")
    op.drop_constraint('ck_scanner_executions_program_id_not_empty', 'scanner_executions', type_='check')
    op.create_foreign_key(
        'fk_scanner_executions_program_id',
        'scanner_executions', 'programs',
        ['program_id'], ['id'],
        ondelete='CASCADE'
    )

    # 2. Create dns_records table
    op.create_table(
        'dns_records',
        sa.Column('id', UUID(), nullable=False),
        sa.Column('host_id', UUID(), nullable=False),
        sa.Column('record_type', sa.String(length=10), nullable=False),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('ttl', sa.Integer(), nullable=True),
        sa.Column('priority', sa.Integer(), nullable=True),
        sa.Column('is_wildcard', sa.Boolean(), nullable=False, server_default='false'),
        sa.CheckConstraint("record_type IN ('A', 'AAAA', 'CNAME', 'MX', 'TXT', 'NS', 'SOA', 'PTR')", name='ck_dns_records_type_valid'),
        sa.CheckConstraint("value != ''", name='ck_dns_records_value_not_empty'),
        sa.ForeignKeyConstraint(['host_id'], ['hosts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('host_id', 'record_type', 'value', name='uq_dns_records_host_type_value')
    )
    op.create_index('idx_dns_records_lookup', 'dns_records', ['host_id', 'record_type'])

    # 3. Create subdomain takeover candidates view
    op.execute("""
        CREATE VIEW subdomain_takeover_candidates AS
        SELECT
            h.host,
            h.program_id,
            dr.value as cname_target,
            CASE
                WHEN dr.value LIKE '%herokuapp.com' THEN 'Heroku'
                WHEN dr.value LIKE '%s3.amazonaws.com' OR dr.value LIKE '%s3-website%' THEN 'AWS S3'
                WHEN dr.value LIKE '%azurewebsites.net' THEN 'Azure'
                WHEN dr.value LIKE '%github.io' THEN 'GitHub Pages'
                WHEN dr.value LIKE '%pantheonsite.io' THEN 'Pantheon'
                WHEN dr.value LIKE '%zendesk.com' THEN 'Zendesk'
                WHEN dr.value LIKE '%shopify.com' THEN 'Shopify'
                WHEN dr.value LIKE '%unbounce.com' THEN 'Unbounce'
                WHEN dr.value LIKE '%fastly.net' THEN 'Fastly'
                WHEN dr.value LIKE '%wordpress.com' THEN 'WordPress'
                WHEN dr.value LIKE '%ghost.io' THEN 'Ghost'
                WHEN dr.value LIKE '%bitbucket.io' THEN 'Bitbucket'
                ELSE 'Other'
            END as platform
        FROM dns_records dr
        JOIN hosts h ON dr.host_id = h.id
        WHERE
            dr.record_type = 'CNAME'
            AND (
                dr.value LIKE '%herokuapp.com'
                OR dr.value LIKE '%s3.amazonaws.com'
                OR dr.value LIKE '%s3-website%'
                OR dr.value LIKE '%azurewebsites.net'
                OR dr.value LIKE '%github.io'
                OR dr.value LIKE '%pantheonsite.io'
                OR dr.value LIKE '%zendesk.com'
                OR dr.value LIKE '%shopify.com'
                OR dr.value LIKE '%unbounce.com'
                OR dr.value LIKE '%fastly.net'
                OR dr.value LIKE '%wordpress.com'
                OR dr.value LIKE '%ghost.io'
                OR dr.value LIKE '%bitbucket.io'
            )
        ORDER BY h.program_id, platform;
    """)

    # 4. Create email security analysis view
    op.execute("""
        CREATE VIEW email_security_analysis AS
        SELECT
            h.host,
            h.program_id,
            MAX(CASE WHEN dr.record_type = 'MX' THEN 'configured' ELSE 'missing' END) as mx_status,
            MAX(CASE WHEN dr.record_type = 'TXT' AND dr.value LIKE 'v=spf1%' THEN dr.value END) as spf_record,
            MAX(CASE WHEN dr.record_type = 'TXT' AND dr.value LIKE '%DMARC1%' THEN dr.value END) as dmarc_record,
            CASE
                WHEN MAX(CASE WHEN dr.record_type = 'TXT' AND dr.value LIKE 'v=spf1%' THEN 1 ELSE 0 END) = 0 THEN 'No SPF'
                WHEN MAX(CASE WHEN dr.record_type = 'TXT' AND dr.value LIKE 'v=spf1%' AND dr.value LIKE '%~all%' THEN 1 ELSE 0 END) = 1 THEN 'SPF Soft Fail'
                WHEN MAX(CASE WHEN dr.record_type = 'TXT' AND dr.value LIKE 'v=spf1%' AND dr.value LIKE '%-all%' THEN 1 ELSE 0 END) = 1 THEN 'SPF Hard Fail'
                ELSE 'SPF Weak'
            END as spf_status,
            CASE
                WHEN MAX(CASE WHEN dr.record_type = 'TXT' AND dr.value LIKE '%DMARC1%' THEN 1 ELSE 0 END) = 0 THEN 'No DMARC'
                WHEN MAX(CASE WHEN dr.record_type = 'TXT' AND dr.value LIKE '%p=reject%' THEN 1 ELSE 0 END) = 1 THEN 'DMARC Reject'
                WHEN MAX(CASE WHEN dr.record_type = 'TXT' AND dr.value LIKE '%p=quarantine%' THEN 1 ELSE 0 END) = 1 THEN 'DMARC Quarantine'
                ELSE 'DMARC Weak'
            END as dmarc_status
        FROM hosts h
        LEFT JOIN dns_records dr ON dr.host_id = h.id
        GROUP BY h.host, h.program_id
        HAVING MAX(CASE WHEN dr.record_type = 'MX' THEN 1 ELSE 0 END) = 1
        ORDER BY h.program_id;
    """)

    # 5. Create DNS infrastructure view
    op.execute("""
        CREATE VIEW dns_infrastructure_view AS
        SELECT
            h.program_id,
            h.host,
            COUNT(DISTINCT CASE WHEN dr.record_type = 'A' THEN dr.value END) as a_records_count,
            COUNT(DISTINCT CASE WHEN dr.record_type = 'AAAA' THEN dr.value END) as aaaa_records_count,
            COUNT(DISTINCT CASE WHEN dr.record_type = 'CNAME' THEN dr.value END) as cname_records_count,
            COUNT(DISTINCT CASE WHEN dr.record_type = 'MX' THEN dr.value END) as mx_records_count,
            COUNT(DISTINCT CASE WHEN dr.record_type = 'TXT' THEN dr.value END) as txt_records_count,
            COUNT(DISTINCT CASE WHEN dr.record_type = 'NS' THEN dr.value END) as ns_records_count,
            array_agg(DISTINCT dr.value) FILTER (WHERE dr.record_type = 'A') as a_records,
            array_agg(DISTINCT dr.value) FILTER (WHERE dr.record_type = 'CNAME') as cname_records,
            h.in_scope
        FROM hosts h
        LEFT JOIN dns_records dr ON dr.host_id = h.id
        GROUP BY h.program_id, h.host, h.in_scope
        ORDER BY h.program_id, h.host;
    """)


def downgrade() -> None:
    """Revert dns_records and scanner_executions changes"""

    # Drop views
    op.execute("DROP VIEW IF EXISTS dns_infrastructure_view;")
    op.execute("DROP VIEW IF EXISTS email_security_analysis;")
    op.execute("DROP VIEW IF EXISTS subdomain_takeover_candidates;")

    # Drop dns_records table
    op.drop_index('idx_dns_records_lookup', table_name='dns_records')
    op.drop_table('dns_records')

    # Revert scanner_executions.program_id
    op.drop_constraint('fk_scanner_executions_program_id', 'scanner_executions', type_='foreignkey')
    op.execute("ALTER TABLE scanner_executions ALTER COLUMN program_id TYPE varchar(36);")
    op.create_check_constraint(
        'ck_scanner_executions_program_id_not_empty',
        'scanner_executions',
        "program_id != ''"
    )
