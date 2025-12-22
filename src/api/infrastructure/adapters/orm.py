"""SQLAlchemy Core tables mapped from domain entities (imperative style)"""
import uuid

from sqlalchemy import (Boolean, CheckConstraint, Column, DateTime, ForeignKey,
                        Index, Integer, MetaData, String, Table, Text,
                        UniqueConstraint)
from sqlalchemy.dialects.postgresql import ARRAY, JSON
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

# Import custom types for cross-database compatibility
from api.infrastructure.database.types import UUID, ArrayType, JSONType

metadata = MetaData()

# ==================== CORE TABLES ====================

programs = Table(
    'programs',
    metadata,
    Column('id', UUID(), primary_key=True, default=uuid.uuid4),
    Column('name', String(255), nullable=False, index=True),
    UniqueConstraint('name', name='uq_programs_name'),
    CheckConstraint("name != ''", name='ck_programs_name_not_empty'),
)

scope_rules = Table(
    'scope_rules',
    metadata,
    Column('id', UUID(), primary_key=True, default=uuid.uuid4),
    Column('program_id', UUID(), ForeignKey('programs.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('rule_type', String(20), nullable=False),
    Column('pattern', String(500), nullable=False),
    CheckConstraint("rule_type IN ('include', 'exclude', 'critical')", name='ck_scope_rules_rule_type'),
    CheckConstraint("pattern != ''", name='ck_scope_rules_pattern_not_empty'),
)

root_inputs = Table(
    'root_inputs',
    metadata,
    Column('id', UUID(), primary_key=True, default=uuid.uuid4),
    Column('program_id', UUID(), ForeignKey('programs.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('value', String(500), nullable=False),
    Column('input_type', String(20), nullable=False),
    CheckConstraint("value != ''", name='ck_root_inputs_value_not_empty'),
    CheckConstraint("input_type IN ('domain', 'url', 'ip_range', 'cidr')", name='ck_root_inputs_input_type'),
)

hosts = Table(
    'hosts',
    metadata,
    Column('id', UUID(), primary_key=True, default=uuid.uuid4),
    Column('program_id', UUID(), ForeignKey('programs.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('host', String(500), nullable=False),
    Column('in_scope', Boolean, default=True, nullable=False),
    Column('cname', JSONType(), default=list),
    UniqueConstraint('program_id', 'host', name='uq_hosts_program_host'),
    Index('idx_hosts_lookup', 'program_id', 'host'),
    CheckConstraint("host != ''", name='ck_hosts_host_not_empty'),
    CheckConstraint("host NOT LIKE '% %'", name='ck_hosts_host_no_spaces'),  # Хосты не содержат пробелы
)

ip_addresses = Table(
    'ip_addresses',
    metadata,
    Column('id', UUID(), primary_key=True, default=uuid.uuid4),
    Column('program_id', UUID(), ForeignKey('programs.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('address', String(45), nullable=False),  # IPv4/IPv6
    Column('in_scope', Boolean, default=True, nullable=False),
    UniqueConstraint('program_id', 'address', name='uq_ip_addresses_program_address'),
    Index('idx_ip_addresses_lookup', 'program_id', 'address'),
    CheckConstraint("address != ''", name='ck_ip_addresses_address_not_empty'),
    
)

host_ips = Table(
    'host_ips',
    metadata,
    Column('id', UUID(), primary_key=True, default=uuid.uuid4),
    Column('host_id', UUID(), ForeignKey('hosts.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('ip_id', UUID(), ForeignKey('ip_addresses.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('source', String(100), nullable=False),
    UniqueConstraint('host_id', 'ip_id', name='uq_host_ips_host_ip'),
    Index('idx_host_ips_lookup', 'host_id', 'ip_id'),
    CheckConstraint("source != ''", name='ck_host_ips_source_not_empty'),
)

services = Table(
    'services',
    metadata,
    Column('id', UUID(), primary_key=True, default=uuid.uuid4),
    Column('ip_id', UUID(), ForeignKey('ip_addresses.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('scheme', String(20), nullable=False),  # http, https
    Column('port', Integer, nullable=False),
    Column('technologies', JSONType(), default=dict),
    UniqueConstraint('ip_id', 'port', name='uq_services_ip_port'),
    Index('idx_services_lookup', 'ip_id', 'port'),
    CheckConstraint("port > 0 AND port <= 65535", name='ck_services_port_range'),
    CheckConstraint("port != 0", name='ck_services_port_not_zero'),
)

endpoints = Table(
    'endpoints',
    metadata,
    Column('id', UUID(), primary_key=True, default=uuid.uuid4),
    Column('host_id', UUID(), ForeignKey('hosts.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('service_id', UUID(), ForeignKey('services.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('path', Text, nullable=False),
    Column('normalized_path', Text, nullable=False),
    Column('methods', ArrayType(String), nullable=False, default=list),
    Column('status_code', Integer, nullable=True),
    UniqueConstraint('host_id', 'path', name='uq_endpoints_host_path'),
    Index('idx_endpoints_lookup', 'host_id', 'normalized_path'),
    Index('idx_endpoints_service', 'service_id'),
    CheckConstraint("path != ''", name='ck_endpoints_path_not_empty'),
    CheckConstraint("normalized_path != ''", name='ck_endpoints_normalized_path_not_empty'),
    CheckConstraint("path LIKE '/%'", name='ck_endpoints_path_starts_with_slash'),  # Путь начинается с /
    CheckConstraint(
        "status_code IS NULL OR (status_code >= 100 AND status_code <= 599)",
        name='ck_endpoints_status_code_range'
    ),
    CheckConstraint(
        "CARDINALITY(methods) > 0", 
        name='ck_endpoints_methods_not_empty'
    ),  
)

# ==================== ENRICHMENT TABLES ====================

input_parameters = Table(
    'input_parameters',
    metadata,
    Column('id', UUID(), primary_key=True, default=uuid.uuid4),
    Column('endpoint_id', UUID(), ForeignKey('endpoints.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('service_id', UUID(), ForeignKey('services.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('name', String(255), nullable=False),
    Column('location', String(20), nullable=False),  # query, body, path, header, cookie
    Column('param_type', String(20), nullable=False, default='string'),
    Column('reflected', Boolean, default=False),
    Column('is_array', Boolean, default=False),
    Column('example_value', String(500), nullable=True),
    UniqueConstraint('endpoint_id', 'location', 'name', name='uq_input_parameters_endpoint_location_name'),
    Index('idx_input_parameters_lookup', 'endpoint_id', 'location', 'name'),
    CheckConstraint("name != ''", name='ck_input_parameters_name_not_empty'),
    CheckConstraint(
        "location IN ('query', 'body', 'path', 'header', 'cookie')",
        name='ck_input_parameters_location_valid'
    ),
    CheckConstraint(
        "param_type IN ('string', 'integer', 'boolean', 'array', 'object', 'file')",
        name='ck_input_parameters_param_type_valid'
    ),
)

headers = Table(
    'headers',
    metadata,
    Column('id', UUID(), primary_key=True, default=uuid.uuid4),
    Column('endpoint_id', UUID(), ForeignKey('endpoints.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('name', String(255), nullable=False),
    Column('value', Text, nullable=False),
    UniqueConstraint('endpoint_id', 'name', name='uq_headers_endpoint_name'),
    Index('idx_headers_lookup', 'endpoint_id', 'name'),
    CheckConstraint("name != ''", name='ck_headers_name_not_empty'),
    CheckConstraint("value != ''", name='ck_headers_value_not_empty'),
)

# ==================== TYPE TABLES ====================

vuln_types = Table(
    'vuln_types',
    metadata,
    Column('id', UUID(), primary_key=True, default=uuid.uuid4),
    Column('code', String(50), nullable=False, index=True),
    Column('severity', String(20), nullable=False),
    Column('category', String(50), nullable=False),
    UniqueConstraint('code', name='uq_vuln_types_code'),
    CheckConstraint("code != ''", name='ck_vuln_types_code_not_empty'),
    CheckConstraint(
        "severity IN ('critical', 'high', 'medium', 'low', 'info')",
        name='ck_vuln_types_severity_valid'
    ),
    CheckConstraint("category != ''", name='ck_vuln_types_category_not_empty'),
)

# ==================== SCANNER TABLES ====================

scanner_templates = Table(
    'scanner_templates',
    metadata,
    Column('id', UUID(), primary_key=True, default=uuid.uuid4),
    Column('name', String(255), nullable=False),
    Column('tool', String(100), nullable=False, index=True),
    Column('command_template', String(1000), nullable=False),
    Column('category', String(100), nullable=False),
    Column('enabled', Boolean, default=True),
    CheckConstraint("name != ''", name='ck_scanner_templates_name_not_empty'),
    CheckConstraint("tool != ''", name='ck_scanner_templates_tool_not_empty'),
    CheckConstraint("command_template != ''", name='ck_scanner_templates_command_template_not_empty'),
    CheckConstraint("category != ''", name='ck_scanner_templates_category_not_empty'),
)

scanner_executions = Table(
    'scanner_executions',
    metadata,
    Column('id', UUID(), primary_key=True, default=uuid.uuid4),
    Column('program_id', String(36), nullable=False, index=True),  # UUID как строка
    Column('status', String(20), nullable=False, index=True),
    Column('template_id', UUID(), ForeignKey('scanner_templates.id', ondelete='CASCADE'), nullable=True, index=True),
    Column('endpoint_id', UUID(), ForeignKey('endpoints.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('error_message', Text, nullable=True),
    Index('idx_scanner_executions_program', 'program_id'),
    CheckConstraint("program_id != ''", name='ck_scanner_executions_program_id_not_empty'),
    CheckConstraint(
        "status IN ('pending', 'running', 'completed', 'failed', 'cancelled')",
        name='ck_scanner_executions_status_valid'
    ),
)

payloads = Table(
    'payloads',
    metadata,
    Column('id', UUID(), primary_key=True, default=uuid.uuid4),
    Column('vuln_type_id', UUID(), ForeignKey('vuln_types.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('payload', Text, nullable=False),
    Column('description', Text, nullable=True),
    Column('tags', ArrayType(String), default=list),
    CheckConstraint("payload != ''", name='ck_payloads_payload_not_empty'),
)

# ==================== RESULTS TABLES ====================

findings = Table(
    'findings',
    metadata,
    Column('id', UUID(), primary_key=True, default=uuid.uuid4),
    Column('program_id', UUID(), ForeignKey('programs.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('vuln_type_id', UUID(), ForeignKey('vuln_types.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('endpoint_id', UUID(), ForeignKey('endpoints.id', ondelete='CASCADE'), nullable=True, index=True),
    Column('parameter_id', UUID(), ForeignKey('input_parameters.id', ondelete='SET NULL'), nullable=True),
    Column('payload_id', UUID(), ForeignKey('payloads.id', ondelete='SET NULL'), nullable=True),
    Column('execution_id', UUID(), ForeignKey('scanner_executions.id', ondelete='SET NULL'), nullable=True),
    Column('description', Text, nullable=False),
    Column('evidence', JSONType(), default=dict),
    Column('verified', Boolean, default=False),
    Column('false_positive', Boolean, default=False),
    Index('idx_findings_program', 'program_id'),
    Index('idx_findings_verified', 'verified'),
    CheckConstraint("description != ''", name='ck_findings_description_not_empty'),
    CheckConstraint("NOT (verified = true AND false_positive = true)", name='ck_findings_state_exclusive'),
)

leaks = Table(
    'leaks',
    metadata,
    Column('id', UUID(), primary_key=True, default=uuid.uuid4),
    Column('program_id', UUID(), ForeignKey('programs.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('endpoint_id', UUID(), ForeignKey('endpoints.id', ondelete='CASCADE'), nullable=True, index=True),
    Column('content', Text, nullable=False),
    Column('verified', Boolean, default=False),
    Column('false_positive', Boolean, default=False),
    Index('idx_leaks_program', 'program_id'),
    CheckConstraint("content != ''", name='ck_leaks_content_not_empty'),
    CheckConstraint("NOT (verified = true AND false_positive = true)", name='ck_leaks_state_exclusive'),
)