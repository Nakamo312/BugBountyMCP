"""Test configuration with proper SQLite support"""
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import event
from sqlalchemy.pool import StaticPool

from api.infrastructure.repositories.program import ProgramRepository


@pytest_asyncio.fixture
async def engine():
    """Create SQLite in-memory engine with proper configuration"""
    # Import models with type override
    import sys
    from unittest.mock import Mock
    
    # Create mock for PostgreSQL-specific types that returns our custom types
    from api.infrastructure.database.types import UUID, JSONType, ArrayType
    from sqlalchemy.dialects import postgresql
    
    # Store originals
    original_types = {
        'UUID': postgresql.UUID,
        'JSONB': postgresql.JSONB,
        'ARRAY': postgresql.ARRAY,
    }
    
    # Override with SQLite-compatible versions
    postgresql.UUID = lambda as_uuid=True: UUID()
    postgresql.JSONB = JSONType()
    
    def array_factory(item_type=None, **kwargs):
        return ArrayType(item_type)
    postgresql.ARRAY = array_factory
    
    # Force reload of models to use new types
    if 'api.infrastructure.database.models' in sys.modules:
        del sys.modules['api.infrastructure.database.models']
    
    from api.infrastructure.database.models import Base
    
    # Create engine
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    
    # Enable foreign keys for SQLite
    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    await engine.dispose()
    
    # Restore original types
    postgresql.UUID = original_types['UUID']
    postgresql.JSONB = original_types['JSONB']
    postgresql.ARRAY = original_types['ARRAY']
    
    # Force reload again to restore original types
    if 'api.infrastructure.database.models' in sys.modules:
        del sys.modules['api.infrastructure.database.models']


@pytest_asyncio.fixture
async def session(engine):
    """Create async session"""
    async_session = async_sessionmaker(
        engine, 
        class_=AsyncSession, 
        expire_on_commit=False
    )
    
    async with async_session() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def program(session):
    """Create test program"""
    repo = ProgramRepository(session)
    program = await repo.create({'name': 'test_program'})
    await session.commit()
    return program