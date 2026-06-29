"""Shared SQLAlchemy metadata for ORM table modules."""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
    text,
)

from api.infrastructure.database.types import UUID, ArrayType, JSONType

metadata = MetaData()
