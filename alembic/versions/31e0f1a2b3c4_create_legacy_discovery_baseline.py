"""Create legacy discovery baseline tables

Revision ID: 31e0f1a2b3c4
Revises: 30e963c8bbe7
Create Date: 2026-06-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "31e0f1a2b3c4"
down_revision: Union[str, None] = "30e963c8bbe7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "programs",
        sa.Column("id", UUID, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.CheckConstraint("name != ''", name="ck_programs_name_not_empty"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_programs_name"),
    )
    op.create_index("ix_programs_name", "programs", ["name"])

    op.create_table(
        "scope_rules",
        sa.Column("id", UUID, nullable=False),
        sa.Column("program_id", UUID, nullable=False),
        sa.Column("action", sa.String(length=10), server_default="include", nullable=False),
        sa.Column("rule_type", sa.String(length=20), nullable=False),
        sa.Column("pattern", sa.String(length=500), nullable=False),
        sa.CheckConstraint("action IN ('include', 'exclude')", name="ck_scope_rules_action"),
        sa.CheckConstraint("rule_type IN ('domain', 'ip_range', 'regex')", name="ck_scope_rules_rule_type"),
        sa.CheckConstraint("pattern != ''", name="ck_scope_rules_pattern_not_empty"),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scope_rules_program_id", "scope_rules", ["program_id"])

    op.create_table(
        "root_inputs",
        sa.Column("id", UUID, nullable=False),
        sa.Column("program_id", UUID, nullable=False),
        sa.Column("value", sa.String(length=500), nullable=False),
        sa.Column("input_type", sa.String(length=20), nullable=False),
        sa.CheckConstraint("value != ''", name="ck_root_inputs_value_not_empty"),
        sa.CheckConstraint("input_type IN ('domain', 'url', 'ip_range', 'cidr')", name="ck_root_inputs_input_type"),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_root_inputs_program_id", "root_inputs", ["program_id"])

    op.create_table(
        "hosts",
        sa.Column("id", UUID, nullable=False),
        sa.Column("program_id", UUID, nullable=False),
        sa.Column("host", sa.String(length=500), nullable=False),
        sa.Column("in_scope", sa.Boolean(), nullable=False),
        sa.Column("cname", JSONB, nullable=True),
        sa.CheckConstraint("host != ''", name="ck_hosts_host_not_empty"),
        sa.CheckConstraint("host NOT LIKE '% %'", name="ck_hosts_host_no_spaces"),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("program_id", "host", name="uq_hosts_program_host"),
    )
    op.create_index("ix_hosts_program_id", "hosts", ["program_id"])
    op.create_index("idx_hosts_lookup", "hosts", ["program_id", "host"])

    op.create_table(
        "ip_addresses",
        sa.Column("id", UUID, nullable=False),
        sa.Column("program_id", UUID, nullable=False),
        sa.Column("address", sa.String(length=45), nullable=False),
        sa.Column("in_scope", sa.Boolean(), nullable=False),
        sa.CheckConstraint("address != ''", name="ck_ip_addresses_address_not_empty"),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("program_id", "address", name="uq_ip_addresses_program_address"),
    )
    op.create_index("ix_ip_addresses_program_id", "ip_addresses", ["program_id"])
    op.create_index("idx_ip_addresses_lookup", "ip_addresses", ["program_id", "address"])

    op.create_table(
        "host_ips",
        sa.Column("id", UUID, nullable=False),
        sa.Column("host_id", UUID, nullable=False),
        sa.Column("ip_id", UUID, nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.CheckConstraint("source != ''", name="ck_host_ips_source_not_empty"),
        sa.ForeignKeyConstraint(["host_id"], ["hosts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ip_id"], ["ip_addresses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("host_id", "ip_id", name="uq_host_ips_host_ip"),
    )
    op.create_index("ix_host_ips_host_id", "host_ips", ["host_id"])
    op.create_index("ix_host_ips_ip_id", "host_ips", ["ip_id"])
    op.create_index("idx_host_ips_lookup", "host_ips", ["host_id", "ip_id"])

    op.create_table(
        "services",
        sa.Column("id", UUID, nullable=False),
        sa.Column("ip_id", UUID, nullable=False),
        sa.Column("scheme", sa.String(length=20), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("technologies", JSONB, nullable=True),
        sa.Column("favicon_hash", sa.String(length=20), nullable=True),
        sa.Column("websocket", sa.Boolean(), nullable=True),
        sa.CheckConstraint("port > 0 AND port <= 65535", name="ck_services_port_range"),
        sa.CheckConstraint("port != 0", name="ck_services_port_not_zero"),
        sa.ForeignKeyConstraint(["ip_id"], ["ip_addresses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ip_id", "port", name="uq_services_ip_port"),
    )
    op.create_index("ix_services_ip_id", "services", ["ip_id"])
    op.create_index("ix_services_favicon_hash", "services", ["favicon_hash"])
    op.create_index("idx_services_lookup", "services", ["ip_id", "port"])

    op.create_table(
        "endpoints",
        sa.Column("id", UUID, nullable=False),
        sa.Column("host_id", UUID, nullable=False),
        sa.Column("service_id", UUID, nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("normalized_path", sa.Text(), nullable=False),
        sa.Column("methods", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.CheckConstraint("path != ''", name="ck_endpoints_path_not_empty"),
        sa.CheckConstraint("normalized_path != ''", name="ck_endpoints_normalized_path_not_empty"),
        sa.CheckConstraint("path LIKE '/%'", name="ck_endpoints_path_starts_with_slash"),
        sa.CheckConstraint(
            "status_code IS NULL OR (status_code >= 100 AND status_code <= 599)",
            name="ck_endpoints_status_code_range",
        ),
        sa.CheckConstraint("CARDINALITY(methods) > 0", name="ck_endpoints_methods_not_empty"),
        sa.ForeignKeyConstraint(["host_id"], ["hosts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("host_id", "path", name="uq_endpoints_host_path"),
    )
    op.create_index("ix_endpoints_host_id", "endpoints", ["host_id"])
    op.create_index("ix_endpoints_service_id", "endpoints", ["service_id"])
    op.create_index("idx_endpoints_lookup", "endpoints", ["host_id", "normalized_path"])
    op.create_index("idx_endpoints_service", "endpoints", ["service_id"])

    op.create_table(
        "input_parameters",
        sa.Column("id", UUID, nullable=False),
        sa.Column("endpoint_id", UUID, nullable=False),
        sa.Column("service_id", UUID, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("location", sa.String(length=20), nullable=False),
        sa.Column("param_type", sa.String(length=20), nullable=False),
        sa.Column("reflected", sa.Boolean(), nullable=True),
        sa.Column("is_array", sa.Boolean(), nullable=True),
        sa.Column("example_value", sa.Text(), nullable=True),
        sa.CheckConstraint("name != ''", name="ck_input_parameters_name_not_empty"),
        sa.CheckConstraint(
            "location IN ('query', 'body', 'path', 'header', 'cookie')",
            name="ck_input_parameters_location_valid",
        ),
        sa.CheckConstraint(
            "param_type IN ('string', 'integer', 'boolean', 'array', 'object', 'file')",
            name="ck_input_parameters_param_type_valid",
        ),
        sa.ForeignKeyConstraint(["endpoint_id"], ["endpoints.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("endpoint_id", "location", "name", name="uq_input_parameters_endpoint_location_name"),
    )
    op.create_index("ix_input_parameters_endpoint_id", "input_parameters", ["endpoint_id"])
    op.create_index("ix_input_parameters_service_id", "input_parameters", ["service_id"])
    op.create_index("idx_input_parameters_lookup", "input_parameters", ["endpoint_id", "location", "name"])

    op.create_table(
        "headers",
        sa.Column("id", UUID, nullable=False),
        sa.Column("endpoint_id", UUID, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.CheckConstraint("name != ''", name="ck_headers_name_not_empty"),
        sa.CheckConstraint("value != ''", name="ck_headers_value_not_empty"),
        sa.ForeignKeyConstraint(["endpoint_id"], ["endpoints.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("endpoint_id", "name", name="uq_headers_endpoint_name"),
    )
    op.create_index("ix_headers_endpoint_id", "headers", ["endpoint_id"])
    op.create_index("idx_headers_lookup", "headers", ["endpoint_id", "name"])

    op.create_table(
        "raw_body",
        sa.Column("id", UUID, nullable=False),
        sa.Column("endpoint_id", UUID, nullable=False),
        sa.Column("body_content", sa.Text(), nullable=False),
        sa.Column("body_hash", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["endpoint_id"], ["endpoints.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("endpoint_id", "body_hash", name="uq_raw_body_endpoint_hash"),
    )
    op.create_index("ix_raw_body_endpoint_id", "raw_body", ["endpoint_id"])
    op.create_index("idx_raw_body_endpoint", "raw_body", ["endpoint_id"])

    op.create_table(
        "vuln_types",
        sa.Column("id", UUID, nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.CheckConstraint("code != ''", name="ck_vuln_types_code_not_empty"),
        sa.CheckConstraint(
            "severity IN ('critical', 'high', 'medium', 'low', 'info')",
            name="ck_vuln_types_severity_valid",
        ),
        sa.CheckConstraint("category != ''", name="ck_vuln_types_category_not_empty"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_vuln_types_code"),
    )
    op.create_index("ix_vuln_types_code", "vuln_types", ["code"])

    op.create_table(
        "scanner_templates",
        sa.Column("id", UUID, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("tool", sa.String(length=100), nullable=False),
        sa.Column("command_template", sa.String(length=1000), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=True),
        sa.CheckConstraint("name != ''", name="ck_scanner_templates_name_not_empty"),
        sa.CheckConstraint("tool != ''", name="ck_scanner_templates_tool_not_empty"),
        sa.CheckConstraint("command_template != ''", name="ck_scanner_templates_command_template_not_empty"),
        sa.CheckConstraint("category != ''", name="ck_scanner_templates_category_not_empty"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scanner_templates_tool", "scanner_templates", ["tool"])

    op.create_table(
        "payloads",
        sa.Column("id", UUID, nullable=False),
        sa.Column("vuln_type_id", UUID, nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tags", postgresql.ARRAY(sa.String()), nullable=True),
        sa.CheckConstraint("payload != ''", name="ck_payloads_payload_not_empty"),
        sa.ForeignKeyConstraint(["vuln_type_id"], ["vuln_types.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_payloads_vuln_type_id", "payloads", ["vuln_type_id"])

    op.create_table(
        "scanner_executions",
        sa.Column("id", UUID, nullable=False),
        sa.Column("program_id", UUID, nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("template_id", UUID, nullable=True),
        sa.Column("endpoint_id", UUID, nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'cancelled')",
            name="ck_scanner_executions_status_valid",
        ),
        sa.ForeignKeyConstraint(["endpoint_id"], ["endpoints.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["template_id"], ["scanner_templates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scanner_executions_program_id", "scanner_executions", ["program_id"])
    op.create_index("ix_scanner_executions_status", "scanner_executions", ["status"])
    op.create_index("ix_scanner_executions_template_id", "scanner_executions", ["template_id"])
    op.create_index("ix_scanner_executions_endpoint_id", "scanner_executions", ["endpoint_id"])
    op.create_index("idx_scanner_executions_program", "scanner_executions", ["program_id"])

    op.create_table(
        "findings",
        sa.Column("id", UUID, nullable=False),
        sa.Column("program_id", UUID, nullable=False),
        sa.Column("vuln_type_id", UUID, nullable=False),
        sa.Column("host_id", UUID, nullable=True),
        sa.Column("endpoint_id", UUID, nullable=True),
        sa.Column("parameter_id", UUID, nullable=True),
        sa.Column("payload_id", UUID, nullable=True),
        sa.Column("execution_id", UUID, nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("evidence", JSONB, nullable=True),
        sa.Column("verified", sa.Boolean(), nullable=True),
        sa.Column("false_positive", sa.Boolean(), nullable=True),
        sa.CheckConstraint("description != ''", name="ck_findings_description_not_empty"),
        sa.CheckConstraint("NOT (verified = true AND false_positive = true)", name="ck_findings_state_exclusive"),
        sa.ForeignKeyConstraint(["endpoint_id"], ["endpoints.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["execution_id"], ["scanner_executions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["host_id"], ["hosts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parameter_id"], ["input_parameters.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["payload_id"], ["payloads.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vuln_type_id"], ["vuln_types.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_findings_program_id", "findings", ["program_id"])
    op.create_index("ix_findings_vuln_type_id", "findings", ["vuln_type_id"])
    op.create_index("ix_findings_host_id", "findings", ["host_id"])
    op.create_index("ix_findings_endpoint_id", "findings", ["endpoint_id"])
    op.create_index("idx_findings_program", "findings", ["program_id"])
    op.create_index("idx_findings_verified", "findings", ["verified"])
    op.create_index("idx_findings_host", "findings", ["host_id"])

    op.create_table(
        "leaks",
        sa.Column("id", UUID, nullable=False),
        sa.Column("program_id", UUID, nullable=False),
        sa.Column("endpoint_id", UUID, nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=True),
        sa.Column("false_positive", sa.Boolean(), nullable=True),
        sa.CheckConstraint("content != ''", name="ck_leaks_content_not_empty"),
        sa.CheckConstraint("NOT (verified = true AND false_positive = true)", name="ck_leaks_state_exclusive"),
        sa.ForeignKeyConstraint(["endpoint_id"], ["endpoints.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("program_id", "content", "endpoint_id", name="uq_leaks_program_id_content_endpoint_id"),
    )
    op.create_index("ix_leaks_program_id", "leaks", ["program_id"])
    op.create_index("ix_leaks_endpoint_id", "leaks", ["endpoint_id"])
    op.create_index("idx_leaks_program", "leaks", ["program_id"])

    op.create_table(
        "dns_records",
        sa.Column("id", UUID, nullable=False),
        sa.Column("host_id", UUID, nullable=False),
        sa.Column("record_type", sa.String(length=10), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("ttl", sa.Integer(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=True),
        sa.Column("is_wildcard", sa.Boolean(), nullable=False),
        sa.CheckConstraint("record_type IN ('A', 'AAAA', 'CNAME', 'MX', 'TXT', 'NS', 'SOA', 'PTR')", name="ck_dns_records_type_valid"),
        sa.CheckConstraint("value != ''", name="ck_dns_records_value_not_empty"),
        sa.ForeignKeyConstraint(["host_id"], ["hosts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("host_id", "record_type", "value", name="uq_dns_records_host_type_value"),
    )
    op.create_index("ix_dns_records_host_id", "dns_records", ["host_id"])
    op.create_index("idx_dns_records_lookup", "dns_records", ["host_id", "record_type"])

    op.create_table(
        "organizations",
        sa.Column("id", UUID, nullable=False),
        sa.Column("program_id", UUID, nullable=False),
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("metadata", JSONB, nullable=False),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("program_id", "name", name="uq_organizations_program_name"),
    )
    op.create_index("ix_organizations_program_id", "organizations", ["program_id"])
    op.create_index("idx_organizations_program", "organizations", ["program_id"])

    op.create_table(
        "asns",
        sa.Column("id", UUID, nullable=False),
        sa.Column("program_id", UUID, nullable=False),
        sa.Column("organization_id", UUID, nullable=True),
        sa.Column("asn_number", sa.Integer(), nullable=False),
        sa.Column("organization_name", sa.String(length=500), nullable=False),
        sa.Column("country_code", sa.String(length=2), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("program_id", "asn_number", name="uq_asns_program_asn"),
    )
    op.create_index("ix_asns_program_id", "asns", ["program_id"])
    op.create_index("ix_asns_organization_id", "asns", ["organization_id"])
    op.create_index("idx_asns_program", "asns", ["program_id"])
    op.create_index("idx_asns_asn_number", "asns", ["asn_number"])

    op.create_table(
        "cidrs",
        sa.Column("id", UUID, nullable=False),
        sa.Column("program_id", UUID, nullable=False),
        sa.Column("asn_id", UUID, nullable=True),
        sa.Column("cidr", sa.String(length=50), nullable=False),
        sa.Column("ip_count", sa.Integer(), nullable=True),
        sa.Column("expanded", sa.Boolean(), nullable=False),
        sa.Column("in_scope", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["asn_id"], ["asns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("program_id", "cidr", name="uq_cidrs_program_cidr"),
    )
    op.create_index("ix_cidrs_program_id", "cidrs", ["program_id"])
    op.create_index("ix_cidrs_asn_id", "cidrs", ["asn_id"])
    op.create_index("idx_cidrs_program", "cidrs", ["program_id"])
    op.create_index("idx_cidrs_asn", "cidrs", ["asn_id"])


def downgrade() -> None:
    op.drop_index("idx_cidrs_asn", table_name="cidrs")
    op.drop_index("idx_cidrs_program", table_name="cidrs")
    op.drop_index("ix_cidrs_asn_id", table_name="cidrs")
    op.drop_index("ix_cidrs_program_id", table_name="cidrs")
    op.drop_table("cidrs")

    op.drop_index("idx_asns_asn_number", table_name="asns")
    op.drop_index("idx_asns_program", table_name="asns")
    op.drop_index("ix_asns_organization_id", table_name="asns")
    op.drop_index("ix_asns_program_id", table_name="asns")
    op.drop_table("asns")

    op.drop_index("idx_organizations_program", table_name="organizations")
    op.drop_index("ix_organizations_program_id", table_name="organizations")
    op.drop_table("organizations")

    op.drop_index("idx_dns_records_lookup", table_name="dns_records")
    op.drop_index("ix_dns_records_host_id", table_name="dns_records")
    op.drop_table("dns_records")

    op.drop_index("idx_leaks_program", table_name="leaks")
    op.drop_index("ix_leaks_endpoint_id", table_name="leaks")
    op.drop_index("ix_leaks_program_id", table_name="leaks")
    op.drop_table("leaks")

    op.drop_index("idx_findings_host", table_name="findings")
    op.drop_index("idx_findings_verified", table_name="findings")
    op.drop_index("idx_findings_program", table_name="findings")
    op.drop_index("ix_findings_endpoint_id", table_name="findings")
    op.drop_index("ix_findings_host_id", table_name="findings")
    op.drop_index("ix_findings_vuln_type_id", table_name="findings")
    op.drop_index("ix_findings_program_id", table_name="findings")
    op.drop_table("findings")

    op.drop_index("idx_scanner_executions_program", table_name="scanner_executions")
    op.drop_index("ix_scanner_executions_endpoint_id", table_name="scanner_executions")
    op.drop_index("ix_scanner_executions_template_id", table_name="scanner_executions")
    op.drop_index("ix_scanner_executions_status", table_name="scanner_executions")
    op.drop_index("ix_scanner_executions_program_id", table_name="scanner_executions")
    op.drop_table("scanner_executions")

    op.drop_index("ix_payloads_vuln_type_id", table_name="payloads")
    op.drop_table("payloads")

    op.drop_index("ix_scanner_templates_tool", table_name="scanner_templates")
    op.drop_table("scanner_templates")

    op.drop_index("ix_vuln_types_code", table_name="vuln_types")
    op.drop_table("vuln_types")

    op.drop_index("idx_raw_body_endpoint", table_name="raw_body")
    op.drop_index("ix_raw_body_endpoint_id", table_name="raw_body")
    op.drop_table("raw_body")

    op.drop_index("idx_headers_lookup", table_name="headers")
    op.drop_index("ix_headers_endpoint_id", table_name="headers")
    op.drop_table("headers")

    op.drop_index("idx_input_parameters_lookup", table_name="input_parameters")
    op.drop_index("ix_input_parameters_service_id", table_name="input_parameters")
    op.drop_index("ix_input_parameters_endpoint_id", table_name="input_parameters")
    op.drop_table("input_parameters")

    op.drop_index("idx_endpoints_service", table_name="endpoints")
    op.drop_index("idx_endpoints_lookup", table_name="endpoints")
    op.drop_index("ix_endpoints_service_id", table_name="endpoints")
    op.drop_index("ix_endpoints_host_id", table_name="endpoints")
    op.drop_table("endpoints")

    op.drop_index("idx_services_lookup", table_name="services")
    op.drop_index("ix_services_favicon_hash", table_name="services")
    op.drop_index("ix_services_ip_id", table_name="services")
    op.drop_table("services")

    op.drop_index("idx_host_ips_lookup", table_name="host_ips")
    op.drop_index("ix_host_ips_ip_id", table_name="host_ips")
    op.drop_index("ix_host_ips_host_id", table_name="host_ips")
    op.drop_table("host_ips")

    op.drop_index("idx_ip_addresses_lookup", table_name="ip_addresses")
    op.drop_index("ix_ip_addresses_program_id", table_name="ip_addresses")
    op.drop_table("ip_addresses")

    op.drop_index("idx_hosts_lookup", table_name="hosts")
    op.drop_index("ix_hosts_program_id", table_name="hosts")
    op.drop_table("hosts")

    op.drop_index("ix_root_inputs_program_id", table_name="root_inputs")
    op.drop_table("root_inputs")

    op.drop_index("ix_scope_rules_program_id", table_name="scope_rules")
    op.drop_table("scope_rules")

    op.drop_index("ix_programs_name", table_name="programs")
    op.drop_table("programs")
