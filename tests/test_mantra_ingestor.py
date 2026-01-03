import pytest
from unittest.mock import AsyncMock
from uuid import uuid4

from api.infrastructure.ingestors.mantra_ingestor import MantraResultIngestor
from api.domain.models import HostModel, EndpointModel, LeakModel


@pytest.fixture
def mock_mantra_uow():
    """Mock MantraUnitOfWork with all required repositories"""
    uow = AsyncMock()

    uow.leaks = AsyncMock()
    uow.hosts = AsyncMock()
    uow.endpoints = AsyncMock()

    uow.commit = AsyncMock()
    uow.rollback = AsyncMock()

    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=None)

    return uow


@pytest.fixture
def mantra_ingestor(mock_mantra_uow):
    return MantraResultIngestor(uow=mock_mantra_uow)


@pytest.fixture
def sample_host():
    return HostModel(
        id=uuid4(),
        program_id=uuid4(),
        host="example.com"
    )


@pytest.fixture
def sample_endpoint(sample_host):
    return EndpointModel(
        id=uuid4(),
        host_id=sample_host.id,
        service_id=uuid4(),
        path="/app.js",
        normalized_path="/app.js",
        methods=["GET"]
    )


@pytest.mark.asyncio
async def test_ingest_creates_leak(mantra_ingestor, mock_mantra_uow, sample_host, sample_endpoint):
    """Test that ingest creates leak with endpoint_id"""
    program_id = uuid4()
    results = [
        {
            "url": "https://example.com/app.js",
            "secret": "sk_live_51H8...",
        }
    ]

    mock_mantra_uow.hosts.get_by_fields = AsyncMock(return_value=sample_host)
    mock_mantra_uow.endpoints.get_by_fields = AsyncMock(return_value=sample_endpoint)
    mock_mantra_uow.leaks.ensure = AsyncMock()

    await mantra_ingestor.ingest(program_id, results)

    mock_mantra_uow.leaks.ensure.assert_called_once_with(
        program_id=program_id,
        content="sk_live_51H8...",
        endpoint_id=sample_endpoint.id,
    )
    mock_mantra_uow.commit.assert_called_once()


@pytest.mark.asyncio
async def test_ingest_creates_leak_without_endpoint(mantra_ingestor, mock_mantra_uow):
    """Test that ingest creates leak with endpoint_id=None when endpoint not found"""
    program_id = uuid4()
    results = [
        {
            "url": "https://example.com/notfound.js",
            "secret": "AKIA...",
        }
    ]

    mock_mantra_uow.hosts.get_by_fields = AsyncMock(return_value=None)
    mock_mantra_uow.leaks.ensure = AsyncMock()

    await mantra_ingestor.ingest(program_id, results)

    mock_mantra_uow.leaks.ensure.assert_called_once_with(
        program_id=program_id,
        content="AKIA...",
        endpoint_id=None,
    )
    mock_mantra_uow.commit.assert_called_once()


@pytest.mark.asyncio
async def test_ingest_handles_url_with_query(mantra_ingestor, mock_mantra_uow, sample_host, sample_endpoint):
    """Test that ingest strips query parameters from URL when finding endpoint"""
    program_id = uuid4()
    results = [
        {
            "url": "https://example.com/app.js?v=123",
            "secret": "ghp_...",
        }
    ]

    mock_mantra_uow.hosts.get_by_fields = AsyncMock(return_value=sample_host)
    mock_mantra_uow.endpoints.get_by_fields = AsyncMock(return_value=sample_endpoint)
    mock_mantra_uow.leaks.ensure = AsyncMock()

    await mantra_ingestor.ingest(program_id, results)

    # Should search for endpoint with path="/app.js" (without query)
    mock_mantra_uow.endpoints.get_by_fields.assert_called_once_with(
        host_id=sample_host.id,
        path="/app.js"
    )


@pytest.mark.asyncio
async def test_ingest_skips_invalid_results(mantra_ingestor, mock_mantra_uow):
    """Test that ingest skips results with missing url or secret"""
    program_id = uuid4()
    results = [
        {"url": "https://example.com/app.js"},  # Missing secret
        {"secret": "sk_live_..."},  # Missing url
        {"url": "https://example.com/valid.js", "secret": "AKIA..."},  # Valid
    ]

    mock_mantra_uow.hosts.get_by_fields = AsyncMock(return_value=None)
    mock_mantra_uow.leaks.ensure = AsyncMock()

    await mantra_ingestor.ingest(program_id, results)

    # Should only create leak for the valid result
    assert mock_mantra_uow.leaks.ensure.call_count == 1


@pytest.mark.asyncio
async def test_ingest_processes_multiple_results(mantra_ingestor, mock_mantra_uow, sample_host, sample_endpoint):
    """Test that ingest processes multiple secrets"""
    program_id = uuid4()
    results = [
        {"url": "https://example.com/app.js", "secret": "secret1"},
        {"url": "https://example.com/app.js", "secret": "secret2"},
        {"url": "https://example.com/app.js", "secret": "secret3"},
    ]

    mock_mantra_uow.hosts.get_by_fields = AsyncMock(return_value=sample_host)
    mock_mantra_uow.endpoints.get_by_fields = AsyncMock(return_value=sample_endpoint)
    mock_mantra_uow.leaks.ensure = AsyncMock()

    await mantra_ingestor.ingest(program_id, results)

    assert mock_mantra_uow.leaks.ensure.call_count == 3
    mock_mantra_uow.commit.assert_called_once()


@pytest.mark.asyncio
async def test_ingest_rollback_on_error(mantra_ingestor, mock_mantra_uow):
    """Test that ingest rolls back transaction on error"""
    program_id = uuid4()
    results = [
        {"url": "https://example.com/app.js", "secret": "secret"},
    ]

    mock_mantra_uow.leaks.ensure = AsyncMock(side_effect=Exception("Database error"))

    with pytest.raises(Exception):
        await mantra_ingestor.ingest(program_id, results)

    mock_mantra_uow.rollback.assert_called_once()


@pytest.mark.asyncio
async def test_find_endpoint_by_url_handles_invalid_url(mantra_ingestor, mock_mantra_uow):
    """Test that _find_endpoint_by_url returns None for invalid URLs"""
    program_id = uuid4()

    result = await mantra_ingestor._find_endpoint_by_url(program_id, "not-a-valid-url")

    assert result is None


@pytest.mark.asyncio
async def test_find_endpoint_by_url_handles_missing_host(mantra_ingestor, mock_mantra_uow):
    """Test that _find_endpoint_by_url returns None when host not found"""
    program_id = uuid4()

    mock_mantra_uow.hosts.get_by_fields = AsyncMock(return_value=None)

    result = await mantra_ingestor._find_endpoint_by_url(program_id, "https://notfound.com/app.js")

    assert result is None


@pytest.mark.asyncio
async def test_find_endpoint_by_url_handles_missing_endpoint(mantra_ingestor, mock_mantra_uow, sample_host):
    """Test that _find_endpoint_by_url returns None when endpoint not found"""
    program_id = uuid4()

    mock_mantra_uow.hosts.get_by_fields = AsyncMock(return_value=sample_host)
    mock_mantra_uow.endpoints.get_by_fields = AsyncMock(return_value=None)

    result = await mantra_ingestor._find_endpoint_by_url(program_id, "https://example.com/notfound.js")

    assert result is None
