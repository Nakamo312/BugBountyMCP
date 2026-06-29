"""Inventory, enrichment, and discovered asset tables."""
import uuid

from .base import (
    ArrayType,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    JSONType,
    Integer,
    LargeBinary,
    String,
    Table,
    Text,
    UUID,
    UniqueConstraint,
    func,
    metadata,
    text,
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
    Column('favicon_hash', String(20), nullable=True, index=True),
    Column('websocket', Boolean, nullable=True, default=False),
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
    Column('example_value', Text, nullable=True),
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


raw_body = Table(
    'raw_body',
    metadata,
    Column('id', UUID(), primary_key=True, default=uuid.uuid4),
    Column('endpoint_id', UUID(), ForeignKey('endpoints.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('body_content', Text, nullable=False),
    Column('body_hash', String(64), nullable=False),
    Index('idx_raw_body_endpoint', 'endpoint_id'),
    UniqueConstraint('endpoint_id', 'body_hash', name='uq_raw_body_endpoint_hash'),
)


dns_records = Table(
    'dns_records',
    metadata,
    Column('id', UUID(), primary_key=True, default=uuid.uuid4),
    Column('host_id', UUID(), ForeignKey('hosts.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('record_type', String(10), nullable=False),
    Column('value', Text, nullable=False),
    Column('ttl', Integer, nullable=True),
    Column('priority', Integer, nullable=True),
    Column('is_wildcard', Boolean, default=False, nullable=False),
    UniqueConstraint('host_id', 'record_type', 'value', name='uq_dns_records_host_type_value'),
    Index('idx_dns_records_lookup', 'host_id', 'record_type'),
    CheckConstraint("record_type IN ('A', 'AAAA', 'CNAME', 'MX', 'TXT', 'NS', 'SOA', 'PTR')", name='ck_dns_records_type_valid'),
    CheckConstraint("value != ''", name='ck_dns_records_value_not_empty'),
)


organizations = Table(
    'organizations',
    metadata,
    Column('id', UUID(), primary_key=True, default=uuid.uuid4),
    Column('program_id', UUID(), ForeignKey('programs.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('name', String(500), nullable=False),
    Column('metadata', JSONType(), default=dict, nullable=False),
    UniqueConstraint('program_id', 'name', name='uq_organizations_program_name'),
    Index('idx_organizations_program', 'program_id'),
)


asns = Table(
    'asns',
    metadata,
    Column('id', UUID(), primary_key=True, default=uuid.uuid4),
    Column('program_id', UUID(), ForeignKey('programs.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('organization_id', UUID(), ForeignKey('organizations.id', ondelete='SET NULL'), nullable=True, index=True),
    Column('asn_number', Integer, nullable=False),
    Column('organization_name', String(500), nullable=False),
    Column('country_code', String(2), nullable=True),
    Column('description', Text, nullable=True),
    UniqueConstraint('program_id', 'asn_number', name='uq_asns_program_asn'),
    Index('idx_asns_program', 'program_id'),
    Index('idx_asns_asn_number', 'asn_number'),
)


cidrs = Table(
    'cidrs',
    metadata,
    Column('id', UUID(), primary_key=True, default=uuid.uuid4),
    Column('program_id', UUID(), ForeignKey('programs.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('asn_id', UUID(), ForeignKey('asns.id', ondelete='CASCADE'), nullable=True, index=True),
    Column('cidr', String(50), nullable=False),
    Column('ip_count', Integer, nullable=True),
    Column('expanded', Boolean, default=False, nullable=False),
    Column('in_scope', Boolean, default=True, nullable=False),
    UniqueConstraint('program_id', 'cidr', name='uq_cidrs_program_cidr'),
    Index('idx_cidrs_program', 'program_id'),
    Index('idx_cidrs_asn', 'asn_id'),
)
