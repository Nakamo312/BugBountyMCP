"""SQLAlchemy Core tables mapped from domain entities (imperative style)"""
import uuid

from sqlalchemy import (Boolean, CheckConstraint, Column, DateTime, Float,
                        ForeignKey, Index, Integer, MetaData, String, Table, Text, func,
                        UniqueConstraint, text)
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
    Column('action', String(10), nullable=False, server_default='include'),
    Column('rule_type', String(20), nullable=False),
    Column('pattern', String(500), nullable=False),
    CheckConstraint("action IN ('include', 'exclude')", name='ck_scope_rules_action'),
    CheckConstraint("rule_type IN ('domain', 'ip_range', 'regex')", name='ck_scope_rules_rule_type'),
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
    Column('program_id', UUID(), ForeignKey('programs.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('status', String(20), nullable=False, index=True),
    Column('template_id', UUID(), ForeignKey('scanner_templates.id', ondelete='CASCADE'), nullable=True, index=True),
    Column('endpoint_id', UUID(), ForeignKey('endpoints.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('error_message', Text, nullable=True),
    Index('idx_scanner_executions_program', 'program_id'),
    CheckConstraint(
        "status IN ('pending', 'running', 'completed', 'failed', 'cancelled')",
        name='ck_scanner_executions_status_valid'
    ),
)

# ==================== TOOL CATALOG PROJECTION TABLES ====================

tool_catalog_snapshots = Table(
    'tool_catalog_snapshots',
    metadata,
    Column('id', UUID(), primary_key=True, default=uuid.uuid4),
    Column('catalog_hash', String(64), nullable=False, index=True),
    Column('source_hash', String(64), nullable=False, index=True),
    Column('source_path', Text, nullable=True),
    Column('schema_version', String(50), nullable=False),
    Column('manifest_json', JSONType(), nullable=False, default=dict),
    Column('created_at', DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column('activated_at', DateTime(timezone=True), nullable=True),
    Column('deactivated_at', DateTime(timezone=True), nullable=True),
    UniqueConstraint('catalog_hash', name='uq_tool_catalog_snapshots_hash'),
    CheckConstraint("catalog_hash != ''", name='ck_tool_catalog_snapshots_hash_not_empty'),
    CheckConstraint("source_hash != ''", name='ck_tool_catalog_snapshots_source_hash_not_empty'),
    CheckConstraint("schema_version != ''", name='ck_tool_catalog_snapshots_schema_not_empty'),
)

tool_catalog_entries = Table(
    'tool_catalog_entries',
    metadata,
    Column('id', UUID(), primary_key=True, default=uuid.uuid4),
    Column('snapshot_id', UUID(), ForeignKey('tool_catalog_snapshots.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('capability_id', String(100), nullable=False, index=True),
    Column('profile_id', String(100), nullable=False, index=True),
    Column('capability_label', String(255), nullable=False),
    Column('profile_label', String(255), nullable=False),
    Column('request_event', String(150), nullable=False, index=True),
    Column('queue', String(100), nullable=False),
    Column('default_profile', String(100), nullable=False),
    Column('mode', String(50), nullable=False),
    Column('scope_policy', String(50), nullable=False),
    Column('safety_class', String(50), nullable=False, index=True),
    Column('allowed_options', JSONType(), nullable=False, default=list),
    Column('requires_approval', Boolean, nullable=False, default=False),
    Column('frontend', JSONType(), nullable=False, default=dict),
    Column('manifest_fragment', JSONType(), nullable=False, default=dict),
    Column('active', Boolean, nullable=False, default=True, index=True),
    Column('created_at', DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint('snapshot_id', 'capability_id', 'profile_id', name='uq_tool_catalog_entries_snapshot_profile'),
    Index('idx_tool_catalog_entries_active_capability', 'active', 'capability_id', 'profile_id'),
    CheckConstraint("capability_id != ''", name='ck_tool_catalog_entries_capability_not_empty'),
    CheckConstraint("profile_id != ''", name='ck_tool_catalog_entries_profile_not_empty'),
    CheckConstraint("request_event != ''", name='ck_tool_catalog_entries_event_not_empty'),
    CheckConstraint("queue != ''", name='ck_tool_catalog_entries_queue_not_empty'),
    CheckConstraint("safety_class IN ('passive', 'safe_active', 'active', 'sensitive')", name='ck_tool_catalog_entries_safety_valid'),
)

# ==================== ORCHESTRATION TABLES ====================

campaigns = Table(
    'campaigns',
    metadata,
    Column('id', UUID(), primary_key=True, default=uuid.uuid4),
    Column('program_id', UUID(), ForeignKey('programs.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('correlation_id', UUID(), nullable=False, index=True),
    Column('workflow_id', UUID(), nullable=True, index=True),
    Column('status', String(30), nullable=False, default='created', index=True),
    Column('metadata', JSONType(), nullable=False, default=dict),
    Column('created_at', DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column('updated_at', DateTime(timezone=True), nullable=False, server_default=func.now()),
    Index('idx_campaigns_program_status', 'program_id', 'status'),
    CheckConstraint(
        "status IN ('created', 'running', 'expanding', 'waiting_for_projections', 'quiescent', 'closed', 'cancelled', 'failed')",
        name='ck_campaigns_status_valid'
    ),
)

action_requests = Table(
    'action_requests',
    metadata,
    Column('id', UUID(), primary_key=True, default=uuid.uuid4),
    Column('program_id', UUID(), ForeignKey('programs.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('catalog_entry_id', UUID(), ForeignKey('tool_catalog_entries.id', ondelete='SET NULL'), nullable=True, index=True),
    Column('kind', String(50), nullable=False),
    Column('capability_id', String(100), nullable=False, index=True),
    Column('profile_id', String(100), nullable=False, index=True),
    Column('requested_by', String(100), nullable=False),
    Column('workflow_id', UUID(), nullable=True, index=True),
    Column('campaign_id', UUID(), ForeignKey('campaigns.id', ondelete='SET NULL'), nullable=True, index=True),
    Column('correlation_id', UUID(), nullable=True, index=True),
    Column('catalog_hash', String(64), nullable=True, index=True),
    Column('metadata', JSONType(), nullable=False, default=dict),
    Column('status', String(30), nullable=False, index=True),
    Column('request', JSONType(), nullable=False, default=dict),
    Column('created_at', DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column('updated_at', DateTime(timezone=True), nullable=False, server_default=func.now()),
    Index('idx_action_requests_program_status', 'program_id', 'status'),
    Index('idx_action_requests_campaign_status', 'campaign_id', 'status'),
    CheckConstraint(
        "status IN ('allowed', 'blocked', 'requires_approval', 'queued', 'rejected')",
        name='ck_action_requests_status_valid'
    ),
)

action_request_targets = Table(
    'action_request_targets',
    metadata,
    Column('id', UUID(), primary_key=True, default=uuid.uuid4),
    Column('action_id', UUID(), ForeignKey('action_requests.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('target', Text, nullable=False),
    Column('position', Integer, nullable=False),
    Column('status', String(30), nullable=False, default='requested', index=True),
    Column('created_at', DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint('action_id', 'position', name='uq_action_request_targets_action_position'),
    Index('idx_action_request_targets_action_status', 'action_id', 'status'),
    CheckConstraint("target != ''", name='ck_action_request_targets_not_empty'),
    CheckConstraint("position >= 0", name='ck_action_request_targets_position_nonnegative'),
    CheckConstraint("status IN ('requested', 'allowed', 'blocked')", name='ck_action_request_targets_status_valid'),
)

action_request_options = Table(
    'action_request_options',
    metadata,
    Column('id', UUID(), primary_key=True, default=uuid.uuid4),
    Column('action_id', UUID(), ForeignKey('action_requests.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('option_key', String(200), nullable=False),
    Column('option_value', JSONType(), nullable=False),
    Column('created_at', DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint('action_id', 'option_key', name='uq_action_request_options_action_key'),
    CheckConstraint("option_key != ''", name='ck_action_request_options_key_not_empty'),
)

scope_decisions = Table(
    'scope_decisions',
    metadata,
    Column('id', UUID(), primary_key=True, default=uuid.uuid4),
    Column('action_id', UUID(), ForeignKey('action_requests.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('status', String(30), nullable=False, index=True),
    Column('scope_policy', String(50), nullable=True),
    Column('reasons', JSONType(), nullable=False, default=list),
    Column('allowed_targets', JSONType(), nullable=False, default=list),
    Column('blocked_targets', JSONType(), nullable=False, default=list),
    Column('metadata', JSONType(), nullable=False, default=dict),
    Column('created_at', DateTime(timezone=True), nullable=False, server_default=func.now()),
    Index('idx_scope_decisions_action_status', 'action_id', 'status'),
    CheckConstraint("status IN ('allowed', 'blocked', 'partial', 'not_evaluated')", name='ck_scope_decisions_status_valid'),
)

approval_requests = Table(
    'approval_requests',
    metadata,
    Column('id', UUID(), primary_key=True, default=uuid.uuid4),
    Column('action_id', UUID(), ForeignKey('action_requests.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('policy_decision_id', UUID(), ForeignKey('policy_decisions.id', ondelete='SET NULL'), nullable=True, index=True),
    Column('status', String(30), nullable=False, default='pending', index=True),
    Column('reason', Text, nullable=True),
    Column('requested_by', String(100), nullable=False, default='policy'),
    Column('created_at', DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column('decided_at', DateTime(timezone=True), nullable=True),
    Index('idx_approval_requests_action_status', 'action_id', 'status'),
    CheckConstraint("status IN ('pending', 'approved', 'rejected', 'cancelled')", name='ck_approval_requests_status_valid'),
)

approval_decisions = Table(
    'approval_decisions',
    metadata,
    Column('id', UUID(), primary_key=True, default=uuid.uuid4),
    Column('approval_request_id', UUID(), ForeignKey('approval_requests.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('action_id', UUID(), ForeignKey('action_requests.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('decision', String(30), nullable=False, index=True),
    Column('decided_by', String(100), nullable=False),
    Column('reason', Text, nullable=True),
    Column('metadata', JSONType(), nullable=False, default=dict),
    Column('created_at', DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint("decision IN ('approved', 'rejected')", name='ck_approval_decisions_valid'),
)

policy_decisions = Table(
    'policy_decisions',
    metadata,
    Column('id', UUID(), primary_key=True, default=uuid.uuid4),
    Column('action_id', UUID(), ForeignKey('action_requests.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('status', String(30), nullable=False, index=True),
    Column('reasons', JSONType(), nullable=False, default=list),
    Column('allowed_targets', JSONType(), nullable=False, default=list),
    Column('blocked_targets', JSONType(), nullable=False, default=list),
    Column('safety_level', String(30), nullable=True, index=True),
    Column('metadata', JSONType(), nullable=False, default=dict),
    Column('catalog_hash', String(64), nullable=True, index=True),
    Column('created_at', DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint(
        "status IN ('allowed', 'blocked', 'requires_approval', 'rejected')",
        name='ck_policy_decisions_status_valid'
    ),
)

jobs = Table(
    'jobs',
    metadata,
    Column('id', UUID(), primary_key=True, default=uuid.uuid4),
    Column('action_id', UUID(), ForeignKey('action_requests.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('program_id', UUID(), ForeignKey('programs.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('capability_id', String(100), nullable=False, index=True),
    Column('profile_id', String(100), nullable=False, index=True),
    Column('status', String(30), nullable=False, index=True),
    Column('correlation_id', UUID(), nullable=False, index=True),
    Column('campaign_id', UUID(), ForeignKey('campaigns.id', ondelete='SET NULL'), nullable=True, index=True),
    Column('created_at', DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column('updated_at', DateTime(timezone=True), nullable=False, server_default=func.now()),
    Index('idx_jobs_program_status', 'program_id', 'status'),
    CheckConstraint(
        "status IN ('queued', 'running', 'completed', 'failed', 'cancelled')",
        name='ck_jobs_status_valid'
    ),
)

runs = Table(
    'runs',
    metadata,
    Column('id', UUID(), primary_key=True, default=uuid.uuid4),
    Column('job_id', UUID(), ForeignKey('jobs.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('program_id', UUID(), ForeignKey('programs.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('node_id', String(100), nullable=True, index=True),
    Column('event_name', String(150), nullable=True, index=True),
    Column('trigger_event_id', UUID(), nullable=True, index=True),
    Column('claim_key', String(64), nullable=True),
    Column('work_key', String(64), nullable=True),
    Column('coalesced_triggers', JSONType(), nullable=True),
    Column('coalesced_trigger_count', Integer, nullable=False, server_default="0"),
    Column('input_fingerprint', String(64), nullable=True, index=True),
    Column('target_fingerprint', String(64), nullable=True, index=True),
    Column('execution_mode', String(20), nullable=False, default='inline'),
    Column('status', String(30), nullable=False, index=True),
    Column('attempt', Integer, nullable=False, default=1),
    Column('leased_at', DateTime(timezone=True), nullable=True),
    Column('lease_owner', String(100), nullable=True),
    Column('lease_expires_at', DateTime(timezone=True), nullable=True),
    Column('started_at', DateTime(timezone=True), nullable=True),
    Column('scanner_started_at', DateTime(timezone=True), nullable=True),
    Column('flushing_at', DateTime(timezone=True), nullable=True),
    Column('next_run_at', DateTime(timezone=True), nullable=True),
    Column('target_count', Integer, nullable=True),
    Column('run_payload', JSONType(), nullable=True),
    Column('next_retry_at', DateTime(timezone=True), nullable=True, index=True),
    Column('finished_at', DateTime(timezone=True), nullable=True),
    Column('terminal_outcome', String(50), nullable=True, index=True),
    Column('retry_reason', String(100), nullable=True),
    Column('needs_reconcile', Boolean, nullable=False, default=False),
    Column('reconcile_reason', Text, nullable=True),
    Column('error', Text, nullable=True),
    Column('created_at', DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column('updated_at', DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint('claim_key', name='uq_runs_claim_key'),
    Index('idx_runs_program_status', 'program_id', 'status'),
    Index('idx_runs_node_event_created', 'node_id', 'event_name', 'created_at'),
    Index('idx_runs_execution_mode_status', 'execution_mode', 'status'),
    Index(
        'idx_runs_scheduled_active_work_key_unique',
        'work_key',
        unique=True,
        postgresql_where=text(
            "execution_mode = 'scheduled' "
            "AND work_key IS NOT NULL "
            "AND status IN ('queued', 'leased', 'running', 'flushing') "
            "AND terminal_outcome IS NULL"
        ),
    ),
    Index(
        'idx_runs_scheduled_work_lookup',
        'node_id',
        'program_id',
        'status',
        'work_key',
        postgresql_where=text(
            "execution_mode = 'scheduled' "
            "AND work_key IS NOT NULL"
        ),
    ),
    Index(
        'idx_runs_scheduled_ready_node_next_run_created',
        'node_id',
        'next_run_at',
        'created_at',
        'id',
        postgresql_where=text(
            "execution_mode = 'scheduled' "
            "AND status = 'queued' "
            "AND terminal_outcome IS NULL "
            "AND needs_reconcile = false"
        ),
    ),
    Index(
        'idx_runs_scheduled_lease_expiry',
        'lease_expires_at',
        'id',
        postgresql_where=text(
            "execution_mode = 'scheduled' "
            "AND status = 'leased'"
        ),
    ),
    CheckConstraint("attempt > 0", name='ck_runs_attempt_positive'),
    CheckConstraint(
        "claim_key IS NULL OR claim_key != ''",
        name='ck_runs_claim_key_not_empty',
    ),
    CheckConstraint(
        "work_key IS NULL OR work_key != ''",
        name='ck_runs_work_key_not_empty',
    ),
    CheckConstraint(
        "execution_mode IN ('inline', 'scheduled')",
        name='ck_runs_execution_mode_valid',
    ),
    CheckConstraint(
        "terminal_outcome IS NULL OR terminal_outcome IN "
        "('completed', 'partial', 'tool_failed', 'skipped', 'policy_blocked')",
        name='ck_runs_terminal_outcome_valid',
    ),
    CheckConstraint(
        "status IN ('queued', 'leased', 'running', 'flushing', 'completed', 'failed', 'dead', 'cancelled')",
        name='ck_runs_status_valid'
    ),
)

event_store = Table(
    'event_store',
    metadata,
    Column('id', UUID(), primary_key=True, default=uuid.uuid4),
    Column('event_id', UUID(), nullable=False, unique=True, index=True),
    Column('event_type', String(150), nullable=False, index=True),
    Column('program_id', UUID(), ForeignKey('programs.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('job_id', UUID(), nullable=True, index=True),
    Column('run_id', UUID(), nullable=True, index=True),
    Column('correlation_id', UUID(), nullable=False, index=True),
    Column('causation_id', UUID(), nullable=True, index=True),
    Column('source', String(100), nullable=False),
    Column('profile', String(100), nullable=True),
    Column('confidence', Float, nullable=False),
    Column('payload', JSONType(), nullable=False, default=dict),
    Column('created_at', DateTime(timezone=True), nullable=False, server_default=func.now()),
    Index('idx_event_store_program_type_created', 'program_id', 'event_type', 'created_at'),
)

event_dispatches = Table(
    'event_dispatches',
    metadata,
    Column('id', UUID(), primary_key=True, default=uuid.uuid4),
    Column('event_id', UUID(), ForeignKey('event_store.event_id', ondelete='CASCADE'), nullable=False, index=True),
    Column('destination', String(100), nullable=False, index=True),
    Column('routing_key', String(255), nullable=False),
    Column('status', String(30), nullable=False, server_default='pending', index=True),
    Column('attempts', Integer, nullable=False, server_default='0'),
    Column('available_at', DateTime(timezone=True), nullable=False, server_default=func.now(), index=True),
    Column('locked_by', String(100), nullable=True),
    Column('locked_until', DateTime(timezone=True), nullable=True),
    Column('dispatched_at', DateTime(timezone=True), nullable=True),
    Column('last_error', Text, nullable=True),
    Column('created_at', DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column('updated_at', DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint('event_id', 'destination', name='uq_event_dispatches_event_destination'),
    Index('idx_event_dispatches_status_available', 'status', 'available_at'),
    Index('idx_event_dispatches_destination_status', 'destination', 'status'),
    CheckConstraint("destination != ''", name='ck_event_dispatches_destination_not_empty'),
    CheckConstraint("routing_key != ''", name='ck_event_dispatches_routing_key_not_empty'),
    CheckConstraint("attempts >= 0", name='ck_event_dispatches_attempts_nonnegative'),
    CheckConstraint(
        "status IN ('pending', 'locked', 'dispatched', 'failed', 'dead')",
        name='ck_event_dispatches_status_valid',
    ),
)

graph_fact_batches = Table(
    'graph_fact_batches',
    metadata,
    Column('id', UUID(), primary_key=True, default=uuid.uuid4),
    Column('program_id', UUID(), ForeignKey('programs.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('produced_by', String(150), nullable=False),
    Column('parser_version', String(100), nullable=False),
    Column('dedupe_key', String(300), nullable=True, unique=True),
    Column('facts_json', JSONType(), nullable=False),
    Column('fact_count', Integer, nullable=False),
    Column('status', String(30), nullable=False, server_default='pending', index=True),
    Column('attempts', Integer, nullable=False, server_default='0'),
    Column('available_at', DateTime(timezone=True), nullable=False, server_default=func.now(), index=True),
    Column('locked_by', String(100), nullable=True),
    Column('locked_until', DateTime(timezone=True), nullable=True),
    Column('created_at', DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column('updated_at', DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column('applied_at', DateTime(timezone=True), nullable=True),
    Column('last_error', Text, nullable=True),
    Index('idx_graph_fact_batches_status_available', 'status', 'available_at'),
    Index('idx_graph_fact_batches_program_created', 'program_id', 'created_at'),
    Index('uq_graph_fact_batches_dedupe_key', 'dedupe_key', unique=True),
    CheckConstraint("produced_by != ''", name='ck_graph_fact_batches_produced_by_not_empty'),
    CheckConstraint("parser_version != ''", name='ck_graph_fact_batches_parser_version_not_empty'),
    CheckConstraint("dedupe_key IS NULL OR dedupe_key != ''", name='ck_graph_fact_batches_dedupe_key_not_empty'),
    CheckConstraint("fact_count > 0", name='ck_graph_fact_batches_fact_count_positive'),
    CheckConstraint("attempts >= 0", name='ck_graph_fact_batches_attempts_nonnegative'),
    CheckConstraint(
        "status IN ('pending', 'locked', 'applied', 'failed', 'dead')",
        name='ck_graph_fact_batches_status_valid',
    ),
)


graph_projection_events = Table(
    'graph_projection_events',
    metadata,
    Column('id', UUID(), primary_key=True, default=uuid.uuid4),
    Column('program_id', UUID(), ForeignKey('programs.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('source_type', String(100), nullable=False),
    Column('source_id', UUID(), nullable=False, index=True),
    Column('event_type', String(150), nullable=False),
    Column('dedupe_key', String(300), nullable=False, unique=True),
    Column('status', String(30), nullable=False, server_default='pending', index=True),
    Column('attempts', Integer, nullable=False, server_default='0'),
    Column('available_at', DateTime(timezone=True), nullable=False, server_default=func.now(), index=True),
    Column('locked_by', String(100), nullable=True),
    Column('locked_until', DateTime(timezone=True), nullable=True),
    Column('created_at', DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column('updated_at', DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column('processed_at', DateTime(timezone=True), nullable=True),
    Column('last_error', Text, nullable=True),
    Index('idx_graph_projection_events_status_available', 'status', 'available_at'),
    Index('idx_graph_projection_events_source', 'source_type', 'source_id'),
    Index('uq_graph_projection_events_dedupe_key', 'dedupe_key', unique=True),
    CheckConstraint("source_type != ''", name='ck_graph_projection_events_source_type_not_empty'),
    CheckConstraint("event_type != ''", name='ck_graph_projection_events_event_type_not_empty'),
    CheckConstraint("dedupe_key != ''", name='ck_graph_projection_events_dedupe_key_not_empty'),
    CheckConstraint("attempts >= 0", name='ck_graph_projection_events_attempts_nonnegative'),
    CheckConstraint(
        "status IN ('pending', 'locked', 'processed', 'failed', 'dead')",
        name='ck_graph_projection_events_status_valid',
    ),
)

raw_artifacts = Table(
    'raw_artifacts',
    metadata,
    Column('id', UUID(), primary_key=True, default=uuid.uuid4),
    Column('program_id', UUID(), ForeignKey('programs.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('job_id', UUID(), nullable=True, index=True),
    Column('run_id', UUID(), nullable=True, index=True),
    Column('node_id', String(100), nullable=False, index=True),
    Column('event_name', String(150), nullable=False, index=True),
    Column('artifact_type', String(50), nullable=False),
    Column('storage_uri', Text, nullable=False),
    Column('sha256', String(64), nullable=False),
    Column('size_bytes', Integer, nullable=False),
    Column('artifact_metadata', JSONType(), nullable=False, default=dict),
    Column('created_at', DateTime(timezone=True), nullable=False, server_default=func.now()),
    Index('idx_raw_artifacts_program_created', 'program_id', 'created_at'),
    Index('idx_raw_artifacts_run', 'run_id'),
    CheckConstraint("artifact_type != ''", name='ck_raw_artifacts_type_not_empty'),
    CheckConstraint("storage_uri != ''", name='ck_raw_artifacts_storage_uri_not_empty'),
    CheckConstraint("size_bytes >= 0", name='ck_raw_artifacts_size_non_negative'),
)

http_observations = Table(
    'http_observations',
    metadata,
    Column('id', UUID(), primary_key=True, default=uuid.uuid4),
    Column('program_id', UUID(), ForeignKey('programs.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('endpoint_id', UUID(), ForeignKey('endpoints.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('service_id', UUID(), ForeignKey('services.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('job_id', UUID(), ForeignKey('jobs.id', ondelete='SET NULL'), nullable=True, index=True),
    Column('run_id', UUID(), ForeignKey('runs.id', ondelete='SET NULL'), nullable=True, index=True),
    Column('correlation_id', UUID(), nullable=True, index=True),
    Column('raw_artifact_id', UUID(), ForeignKey('raw_artifacts.id', ondelete='SET NULL'), nullable=True, index=True),
    Column('method', String(10), nullable=False),
    Column('url', Text, nullable=False),
    Column('status_code', Integer, nullable=True),
    Column('content_type', Text, nullable=True),
    Column('title', Text, nullable=True),
    Column('body_sha256', String(64), nullable=True),
    Column('body_size_bytes', Integer, nullable=True),
    Column('body_artifact_id', UUID(), ForeignKey('raw_artifacts.id', ondelete='SET NULL'), nullable=True, index=True),
    Column('body_preview', Text, nullable=True),
    Column('source_tool', String(100), nullable=False),
    Column('metadata', JSONType(), nullable=False, default=dict),
    Column('observed_at', DateTime(timezone=True), nullable=False, server_default=func.now()),
    Index('idx_http_observations_program_observed', 'program_id', 'observed_at'),
    Index('idx_http_observations_endpoint_observed', 'endpoint_id', 'observed_at'),
    Index('idx_http_observations_run_observed', 'run_id', 'observed_at'),
    CheckConstraint("method != ''", name='ck_http_observations_method_not_empty'),
    CheckConstraint("url != ''", name='ck_http_observations_url_not_empty'),
    CheckConstraint("source_tool != ''", name='ck_http_observations_source_tool_not_empty'),
    CheckConstraint(
        "status_code IS NULL OR (status_code >= 100 AND status_code <= 599)",
        name='ck_http_observations_status_code_range'
    ),
    CheckConstraint(
        "body_size_bytes IS NULL OR body_size_bytes >= 0",
        name='ck_http_observations_body_size_non_negative'
    ),
)

http_observation_headers = Table(
    'http_observation_headers',
    metadata,
    Column('id', UUID(), primary_key=True, default=uuid.uuid4),
    Column('observation_id', UUID(), ForeignKey('http_observations.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('name', String(255), nullable=False),
    Column('value', Text, nullable=False),
    Column('ordinal', Integer, nullable=False, default=0),
    Index('idx_http_observation_headers_lookup', 'observation_id', 'name'),
    CheckConstraint("name != ''", name='ck_http_observation_headers_name_not_empty'),
    CheckConstraint("ordinal >= 0", name='ck_http_observation_headers_ordinal_non_negative'),
)

# ==================== RESEARCH TABLES ====================

research_producer_runs = Table(
    'research_producer_runs',
    metadata,
    Column('id', UUID(), primary_key=True, default=uuid.uuid4),
    Column('producer_name', String(100), nullable=False, index=True),
    Column('producer_version', String(100), nullable=False),
    Column('rule_version', String(100), nullable=False),
    Column('status', String(30), nullable=False, index=True),
    Column('input_watermark', Text, nullable=True),
    Column('stats_json', JSONType(), nullable=False, default=dict),
    Column('error', Text, nullable=True),
    Column('started_at', DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column('finished_at', DateTime(timezone=True), nullable=True),
    Index('idx_research_producer_runs_status_started', 'status', 'started_at'),
    CheckConstraint("producer_name != ''", name='ck_research_producer_runs_name_not_empty'),
    CheckConstraint("producer_version != ''", name='ck_research_producer_runs_version_not_empty'),
    CheckConstraint("rule_version != ''", name='ck_research_producer_runs_rule_version_not_empty'),
    CheckConstraint(
        "status IN ('running', 'completed', 'failed')",
        name='ck_research_producer_runs_status_valid',
    ),
)

research_signals = Table(
    'research_signals',
    metadata,
    Column('id', UUID(), primary_key=True, default=uuid.uuid4),
    Column('program_id', UUID(), ForeignKey('programs.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('producer_run_id', UUID(), ForeignKey('research_producer_runs.id', ondelete='SET NULL'), nullable=True, index=True),
    Column('signal_type', String(100), nullable=False, index=True),
    Column('signal_version', String(100), nullable=False),
    Column('rule_id', String(100), nullable=False),
    Column('rule_version', String(100), nullable=False),
    Column('asset_type', String(50), nullable=True, index=True),
    Column('asset_id', Text, nullable=True),
    Column('observation_id', UUID(), ForeignKey('http_observations.id', ondelete='SET NULL'), nullable=True, index=True),
    Column('evidence_fingerprint', String(64), nullable=False),
    Column('confidence', Float, nullable=False),
    Column('payload_json', JSONType(), nullable=False, default=dict),
    Column('created_at', DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint(
        'program_id',
        'signal_type',
        'signal_version',
        'evidence_fingerprint',
        name='uq_research_signal_fingerprint',
    ),
    Index('idx_research_signals_program_type_created', 'program_id', 'signal_type', 'created_at'),
    CheckConstraint("signal_type != ''", name='ck_research_signals_type_not_empty'),
    CheckConstraint("signal_version != ''", name='ck_research_signals_version_not_empty'),
    CheckConstraint("rule_id != ''", name='ck_research_signals_rule_id_not_empty'),
    CheckConstraint("rule_version != ''", name='ck_research_signals_rule_version_not_empty'),
    CheckConstraint("evidence_fingerprint != ''", name='ck_research_signals_fingerprint_not_empty'),
    CheckConstraint(
        "confidence >= 0 AND confidence <= 1",
        name='ck_research_signals_confidence_range',
    ),
)

research_hypotheses = Table(
    'research_hypotheses',
    metadata,
    Column('id', UUID(), primary_key=True, default=uuid.uuid4),
    Column('program_id', UUID(), ForeignKey('programs.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('hypothesis_type', String(100), nullable=False, index=True),
    Column('hypothesis_fingerprint', String(64), nullable=False),
    Column('status', String(30), nullable=False, index=True),
    Column('state_version', Integer, nullable=False, default=1),
    Column('priority_score', Integer, nullable=False, default=0),
    Column('confidence', Float, nullable=False, default=0),
    Column('severity_guess', String(20), nullable=True, index=True),
    Column('safety_level', String(30), nullable=False, default='passive'),
    Column('score_version', String(100), nullable=False),
    Column('inputs_hash', String(64), nullable=False),
    Column('source_signal_fingerprints', JSONType(), nullable=False, default=list),
    Column('duplicate_of_hypothesis_id', UUID(), ForeignKey('research_hypotheses.id', ondelete='SET NULL'), nullable=True, index=True),
    Column('first_seen', DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column('last_seen', DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column('updated_at', DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint(
        'program_id',
        'hypothesis_type',
        'hypothesis_fingerprint',
        name='uq_research_hypothesis_fingerprint',
    ),
    Index('idx_research_hypotheses_program_status_score', 'program_id', 'status', 'priority_score'),
    CheckConstraint("hypothesis_type != ''", name='ck_research_hypotheses_type_not_empty'),
    CheckConstraint("hypothesis_fingerprint != ''", name='ck_research_hypotheses_fingerprint_not_empty'),
    CheckConstraint("state_version > 0", name='ck_research_hypotheses_state_version_positive'),
    CheckConstraint(
        "status IN ('new', 'needs_verification', 'reviewing', 'dismissed', 'duplicate', 'promoted', 'stale')",
        name='ck_research_hypotheses_status_valid',
    ),
    CheckConstraint(
        "priority_score >= 0 AND priority_score <= 100",
        name='ck_research_hypotheses_priority_range',
    ),
    CheckConstraint(
        "confidence >= 0 AND confidence <= 1",
        name='ck_research_hypotheses_confidence_range',
    ),
    CheckConstraint(
        "duplicate_of_hypothesis_id IS NULL OR duplicate_of_hypothesis_id != id",
        name='ck_research_hypotheses_duplicate_not_self',
    ),
    CheckConstraint(
        "status != 'duplicate' OR duplicate_of_hypothesis_id IS NOT NULL",
        name='ck_research_hypotheses_duplicate_status_requires_ref',
    ),
    CheckConstraint(
        "duplicate_of_hypothesis_id IS NULL OR status = 'duplicate'",
        name='ck_research_hypotheses_duplicate_ref_requires_status',
    ),
)

research_hypothesis_evidence = Table(
    'research_hypothesis_evidence',
    metadata,
    Column('id', UUID(), primary_key=True, default=uuid.uuid4),
    Column('hypothesis_id', UUID(), ForeignKey('research_hypotheses.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('ref_type', String(50), nullable=False, index=True),
    Column('ref_id', Text, nullable=False),
    Column('field_path', Text, nullable=True),
    Column('role', String(30), nullable=False),
    Column('claim_type', String(100), nullable=False),
    Column('claim', Text, nullable=False),
    Column('evidence_fingerprint', String(64), nullable=False),
    Column('safe_excerpt', Text, nullable=True),
    Column('safe_excerpt_truncated', Boolean, nullable=False, default=False),
    Column('safe_excerpt_hash', String(64), nullable=True),
    Column('evidence_source', String(30), nullable=False),
    Column('normalized_content_hash', String(64), nullable=True),
    Column('sanitized_content_hash', String(64), nullable=True),
    Column('sanitizer_version', String(100), nullable=False),
    Column('redaction_policy_version', String(100), nullable=False),
    Column('sensitivity_level', String(50), nullable=False),
    Column('redaction_rules_triggered', JSONType(), nullable=False, default=list),
    Column('safe_for_search', Boolean, nullable=False, default=False),
    Column('safe_for_embedding', Boolean, nullable=False, default=False),
    Column('safe_for_llm', Boolean, nullable=False, default=False),
    Column('created_at', DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint(
        'hypothesis_id',
        'evidence_fingerprint',
        name='uq_research_hypothesis_evidence_fingerprint',
    ),
    Index('idx_research_evidence_hypothesis_role', 'hypothesis_id', 'role'),
    CheckConstraint("ref_type != ''", name='ck_research_evidence_ref_type_not_empty'),
    CheckConstraint("ref_id != ''", name='ck_research_evidence_ref_id_not_empty'),
    CheckConstraint("claim_type != ''", name='ck_research_evidence_claim_type_not_empty'),
    CheckConstraint("claim != ''", name='ck_research_evidence_claim_not_empty'),
    CheckConstraint("evidence_fingerprint != ''", name='ck_research_evidence_fingerprint_not_empty'),
    CheckConstraint(
        "role IN ('primary', 'supporting', 'context', 'contradicting')",
        name='ck_research_evidence_role_valid',
    ),
    CheckConstraint(
        "evidence_source IN ('sanitizer', 'metadata_only', 'manual', 'legacy')",
        name='ck_research_evidence_source_valid',
    ),
    CheckConstraint(
        "safe_excerpt IS NULL OR safe_for_search = true",
        name='ck_research_evidence_safe_excerpt_requires_search_safe',
    ),
)

research_hypothesis_events = Table(
    'research_hypothesis_events',
    metadata,
    Column('id', UUID(), primary_key=True, default=uuid.uuid4),
    Column('hypothesis_id', UUID(), ForeignKey('research_hypotheses.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('event_type', String(100), nullable=False, index=True),
    Column('aggregate_version', Integer, nullable=False),
    Column('actor', String(100), nullable=False),
    Column('reason', Text, nullable=True),
    Column('payload_json', JSONType(), nullable=False, default=dict),
    Column('created_at', DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint(
        'hypothesis_id',
        'aggregate_version',
        name='uq_research_hypothesis_events_version',
    ),
    Index('idx_research_hypothesis_events_hypothesis_version', 'hypothesis_id', 'aggregate_version'),
    CheckConstraint("event_type != ''", name='ck_research_hypothesis_events_type_not_empty'),
    CheckConstraint("actor != ''", name='ck_research_hypothesis_events_actor_not_empty'),
    CheckConstraint(
        "aggregate_version > 0",
        name='ck_research_hypothesis_events_aggregate_version_positive',
    ),
)

research_hypothesis_score_history = Table(
    'research_hypothesis_score_history',
    metadata,
    Column('id', UUID(), primary_key=True, default=uuid.uuid4),
    Column('hypothesis_id', UUID(), ForeignKey('research_hypotheses.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('score_version', String(100), nullable=False),
    Column('priority_score', Integer, nullable=False),
    Column('confidence', Float, nullable=False),
    Column('severity_guess', String(20), nullable=True),
    Column('safety_level', String(30), nullable=False),
    Column('inputs_hash', String(64), nullable=False),
    Column('factors_json', JSONType(), nullable=False, default=dict),
    Column('created_at', DateTime(timezone=True), nullable=False, server_default=func.now()),
    Index('idx_research_score_history_hypothesis_created', 'hypothesis_id', 'created_at'),
    CheckConstraint("score_version != ''", name='ck_research_score_history_version_not_empty'),
    CheckConstraint("inputs_hash != ''", name='ck_research_score_history_inputs_hash_not_empty'),
    CheckConstraint(
        "priority_score >= 0 AND priority_score <= 100",
        name='ck_research_score_history_priority_range',
    ),
    CheckConstraint(
        "confidence >= 0 AND confidence <= 1",
        name='ck_research_score_history_confidence_range',
    ),
)

research_suppression_rules = Table(
    'research_suppression_rules',
    metadata,
    Column('id', UUID(), primary_key=True, default=uuid.uuid4),
    Column('program_id', UUID(), ForeignKey('programs.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('scope', String(50), nullable=False),
    Column('match_type', String(50), nullable=False),
    Column('match_value', Text, nullable=False),
    Column('match_fingerprint', String(64), nullable=False),
    Column('reason', Text, nullable=False),
    Column('enabled', Boolean, nullable=False, default=True),
    Column('created_from_hypothesis_id', UUID(), ForeignKey('research_hypotheses.id', ondelete='SET NULL'), nullable=True, index=True),
    Column('expires_at', DateTime(timezone=True), nullable=True),
    Column('created_at', DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint(
        'program_id',
        'scope',
        'match_type',
        'match_fingerprint',
        name='uq_research_suppression_fingerprint',
    ),
    Index('idx_research_suppression_program_scope', 'program_id', 'scope'),
    CheckConstraint("scope != ''", name='ck_research_suppression_scope_not_empty'),
    CheckConstraint("match_type != ''", name='ck_research_suppression_match_type_not_empty'),
    CheckConstraint("match_value != ''", name='ck_research_suppression_match_value_not_empty'),
    CheckConstraint("match_fingerprint != ''", name='ck_research_suppression_fingerprint_not_empty'),
    CheckConstraint("reason != ''", name='ck_research_suppression_reason_not_empty'),
    CheckConstraint(
        "scope IN ('global', 'program', 'asset', 'hypothesis_type', 'signal_type', 'dedupe_group')",
        name='ck_research_suppression_scope_valid',
    ),
    CheckConstraint(
        "match_type IN ('exact', 'fingerprint', 'prefix', 'regex', 'tag')",
        name='ck_research_suppression_match_type_valid',
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
    Column('host_id', UUID(), ForeignKey('hosts.id', ondelete='CASCADE'), nullable=True, index=True),
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
    Index('idx_findings_host', 'host_id'),
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
    UniqueConstraint('program_id', 'content', 'endpoint_id', name='uq_leaks_program_id_content_endpoint_id'),
    CheckConstraint("content != ''", name='ck_leaks_content_not_empty'),
    CheckConstraint("NOT (verified = true AND false_positive = true)", name='ck_leaks_state_exclusive'),
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
