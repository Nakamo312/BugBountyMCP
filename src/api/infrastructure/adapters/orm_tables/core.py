"""Program and scope boundary tables."""
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
