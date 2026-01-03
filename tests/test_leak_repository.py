import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from api.domain.models import LeakModel
from api.infrastructure.repositories.adapters.leak import SQLAlchemyLeakRepository


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def leak_repository(mock_session):
    return SQLAlchemyLeakRepository(session=mock_session)


@pytest.mark.asyncio
async def test_find_by_program_calls_find_many(leak_repository, mock_session):
    """Test that find_by_program delegates to find_many"""
    program_id = uuid4()

    mock_result = AsyncMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_result

    leak_repository.find_many = AsyncMock(return_value=[])

    await leak_repository.find_by_program(program_id)

    leak_repository.find_many.assert_called_once_with(filters={"program_id": program_id})


@pytest.mark.asyncio
async def test_ensure_creates_leak_model(leak_repository, mock_session):
    """Test that ensure creates LeakModel with correct fields"""
    program_id = uuid4()
    endpoint_id = uuid4()

    leak_repository.upsert = AsyncMock(return_value=LeakModel(
        id=uuid4(),
        program_id=program_id,
        content="AKIA...",
        endpoint_id=endpoint_id,
    ))

    result = await leak_repository.ensure(
        program_id=program_id,
        content="AKIA...",
        endpoint_id=endpoint_id,
    )

    leak_repository.upsert.assert_called_once()
    call_args = leak_repository.upsert.call_args[0][0]
    assert isinstance(call_args, LeakModel)
    assert call_args.program_id == program_id
    assert call_args.content == "AKIA..."
    assert call_args.endpoint_id == endpoint_id


@pytest.mark.asyncio
async def test_ensure_with_null_endpoint(leak_repository, mock_session):
    """Test that ensure accepts None for endpoint_id"""
    program_id = uuid4()

    leak_repository.upsert = AsyncMock(return_value=LeakModel(
        id=uuid4(),
        program_id=program_id,
        content="secret",
        endpoint_id=None,
    ))

    result = await leak_repository.ensure(
        program_id=program_id,
        content="secret",
        endpoint_id=None,
    )

    leak_repository.upsert.assert_called_once()
    call_args = leak_repository.upsert.call_args[0][0]
    assert call_args.endpoint_id is None


@pytest.mark.asyncio
async def test_ensure_uses_correct_conflict_fields(leak_repository, mock_session):
    """Test that ensure uses program_id, content, endpoint_id as conflict fields"""
    program_id = uuid4()

    leak_repository.upsert = AsyncMock(return_value=LeakModel(
        id=uuid4(),
        program_id=program_id,
        content="test",
        endpoint_id=None,
    ))

    await leak_repository.ensure(
        program_id=program_id,
        content="test",
        endpoint_id=None,
    )

    leak_repository.upsert.assert_called_once()
    call_kwargs = leak_repository.upsert.call_args[1]
    assert call_kwargs["conflict_fields"] == ["program_id", "content", "endpoint_id"]
