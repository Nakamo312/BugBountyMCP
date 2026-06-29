"""Scanner catalog, execution, vulnerability type, and payload tables."""
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
