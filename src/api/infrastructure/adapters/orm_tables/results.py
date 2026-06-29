"""Finding and leak result tables."""
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
