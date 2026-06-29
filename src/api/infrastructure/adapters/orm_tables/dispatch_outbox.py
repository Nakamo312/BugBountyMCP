"""Domain event store and dispatch outbox tables."""
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
