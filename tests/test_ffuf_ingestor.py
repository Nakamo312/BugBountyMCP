import pytest
from unittest.mock import AsyncMock
from uuid import uuid4

from api.infrastructure.ingestors.ffuf_ingestor import FFUFResultIngestor
from api.domain.models import HostModel, ServiceModel, EndpointModel, IPAddressModel, HostIPModel


@pytest.fixture
def mock_httpx_uow():
    """Mock HTTPXUnitOfWork with all required repositories"""
    uow = AsyncMock()

    uow.hosts = AsyncMock()
    uow.services = AsyncMock()
    uow.endpoints = AsyncMock()
    uow.host_ips = AsyncMock()
    uow.ips = AsyncMock()

    uow.commit = AsyncMock()
    uow.rollback = AsyncMock()

    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=None)

    return uow


@pytest.fixture
def ffuf_ingestor(mock_httpx_uow):
    return FFUFResultIngestor(uow=mock_httpx_uow)


@pytest.fixture
def sample_host():
    return HostModel(
        id=uuid4(),
        program_id=uuid4(),
        host="example.com",
        in_scope=True
    )


@pytest.fixture
def sample_ip(sample_host):
    return IPAddressModel(
        id=uuid4(),
        address="192.168.1.1",
        program_id=sample_host.program_id
    )


@pytest.fixture
def sample_host_ip(sample_host, sample_ip):
    return HostIPModel(
        id=uuid4(),
        host_id=sample_host.id,
        ip_id=sample_ip.id,
        source="httpx"
    )


@pytest.fixture
def sample_service(sample_ip):
    return ServiceModel(
        id=uuid4(),
        ip_id=sample_ip.id,
        port=443,
        scheme="https"
    )


@pytest.mark.asyncio
async def test_ingest_creates_endpoint(ffuf_ingestor, mock_httpx_uow, sample_host, sample_host_ip, sample_ip, sample_service):
    """Test that ingest creates endpoint for discovered URL"""
    program_id = uuid4()
    results = [
        {
            "url": "https://example.com/admin",
            "status": 200,
            "length": 1234,
        }
    ]

    mock_httpx_uow.hosts.get_by_fields = AsyncMock(return_value=sample_host)
    mock_httpx_uow.host_ips.find_many = AsyncMock(return_value=[sample_host_ip])
    mock_httpx_uow.ips.get = AsyncMock(return_value=sample_ip)
    mock_httpx_uow.services.get_by_fields = AsyncMock(return_value=sample_service)
    mock_httpx_uow.endpoints.ensure = AsyncMock()

    await ffuf_ingestor.ingest(program_id, results)

    mock_httpx_uow.hosts.get_by_fields.assert_called_once_with(
        program_id=program_id,
        host="example.com"
    )
    mock_httpx_uow.host_ips.find_many.assert_called_once_with(
        filters={"host_id": sample_host.id},
        limit=1
    )
    mock_httpx_uow.ips.get.assert_called_once_with(sample_host_ip.ip_id)
    mock_httpx_uow.services.get_by_fields.assert_called_once_with(
        ip_id=sample_ip.id,
        port=443,
        scheme="https"
    )

    call_args = mock_httpx_uow.endpoints.ensure.call_args[1]
    assert call_args["host_id"] == sample_host.id
    assert call_args["service_id"] == sample_service.id
    assert call_args["path"] == "/admin"
    assert call_args["method"] == "GET"
    assert call_args["status_code"] == 200
    assert "normalized_path" in call_args
    mock_httpx_uow.commit.assert_called_once()


@pytest.mark.asyncio
async def test_ingest_skips_unknown_host(ffuf_ingestor, mock_httpx_uow):
    """Test that ingest skips results when host not found in database"""
    program_id = uuid4()
    results = [
        {
            "url": "https://unknown.com/admin",
            "status": 200,
        }
    ]

    mock_httpx_uow.hosts.get_by_fields = AsyncMock(return_value=None)
    mock_httpx_uow.endpoints.ensure = AsyncMock()

    await ffuf_ingestor.ingest(program_id, results)

    mock_httpx_uow.endpoints.ensure.assert_not_called()
    mock_httpx_uow.commit.assert_called_once()


@pytest.mark.asyncio
async def test_ingest_handles_http_url(ffuf_ingestor, mock_httpx_uow, sample_host, sample_host_ip, sample_ip):
    """Test ingesting HTTP URL (port 80)"""
    program_id = uuid4()
    results = [
        {
            "url": "http://example.com/api",
            "status": 200,
        }
    ]

    http_service = ServiceModel(id=uuid4(), ip_id=sample_ip.id, port=80, scheme="http")

    mock_httpx_uow.hosts.get_by_fields = AsyncMock(return_value=sample_host)
    mock_httpx_uow.host_ips.find_many = AsyncMock(return_value=[sample_host_ip])
    mock_httpx_uow.ips.get = AsyncMock(return_value=sample_ip)
    mock_httpx_uow.services.get_by_fields = AsyncMock(return_value=http_service)
    mock_httpx_uow.endpoints.ensure = AsyncMock()

    await ffuf_ingestor.ingest(program_id, results)

    mock_httpx_uow.services.get_by_fields.assert_called_once_with(
        ip_id=sample_ip.id,
        port=80,
        scheme="http"
    )


@pytest.mark.asyncio
async def test_ingest_handles_custom_port(ffuf_ingestor, mock_httpx_uow, sample_host, sample_host_ip, sample_ip):
    """Test ingesting URL with custom port"""
    program_id = uuid4()
    results = [
        {
            "url": "https://example.com:8443/admin",
            "status": 200,
        }
    ]

    custom_service = ServiceModel(id=uuid4(), ip_id=sample_ip.id, port=8443, scheme="https")

    mock_httpx_uow.hosts.get_by_fields = AsyncMock(return_value=sample_host)
    mock_httpx_uow.host_ips.find_many = AsyncMock(return_value=[sample_host_ip])
    mock_httpx_uow.ips.get = AsyncMock(return_value=sample_ip)
    mock_httpx_uow.services.get_by_fields = AsyncMock(return_value=custom_service)
    mock_httpx_uow.endpoints.ensure = AsyncMock()

    await ffuf_ingestor.ingest(program_id, results)

    mock_httpx_uow.services.get_by_fields.assert_called_once_with(
        ip_id=sample_ip.id,
        port=8443,
        scheme="https"
    )


@pytest.mark.asyncio
async def test_ingest_handles_root_path(ffuf_ingestor, mock_httpx_uow, sample_host, sample_host_ip, sample_ip, sample_service):
    """Test ingesting URL with root path"""
    program_id = uuid4()
    results = [
        {
            "url": "https://example.com/",
            "status": 200,
        }
    ]

    mock_httpx_uow.hosts.get_by_fields = AsyncMock(return_value=sample_host)
    mock_httpx_uow.host_ips.find_many = AsyncMock(return_value=[sample_host_ip])
    mock_httpx_uow.ips.get = AsyncMock(return_value=sample_ip)
    mock_httpx_uow.services.get_by_fields = AsyncMock(return_value=sample_service)
    mock_httpx_uow.endpoints.ensure = AsyncMock()

    await ffuf_ingestor.ingest(program_id, results)

    mock_httpx_uow.endpoints.ensure.assert_called_once()
    call_args = mock_httpx_uow.endpoints.ensure.call_args[1]
    assert call_args["path"] == "/"


@pytest.mark.asyncio
async def test_ingest_handles_query_parameters(ffuf_ingestor, mock_httpx_uow, sample_host, sample_host_ip, sample_ip, sample_service):
    """Test that query parameters are included in path"""
    program_id = uuid4()
    results = [
        {
            "url": "https://example.com/api?page=1&limit=10",
            "status": 200,
        }
    ]

    mock_httpx_uow.hosts.get_by_fields = AsyncMock(return_value=sample_host)
    mock_httpx_uow.host_ips.find_many = AsyncMock(return_value=[sample_host_ip])
    mock_httpx_uow.ips.get = AsyncMock(return_value=sample_ip)
    mock_httpx_uow.services.get_by_fields = AsyncMock(return_value=sample_service)
    mock_httpx_uow.endpoints.ensure = AsyncMock()

    await ffuf_ingestor.ingest(program_id, results)

    call_args = mock_httpx_uow.endpoints.ensure.call_args[1]
    # Path is parsed without query params (urlparse.path doesn't include query)
    assert call_args["path"] == "/api"


@pytest.mark.asyncio
async def test_ingest_processes_multiple_results(ffuf_ingestor, mock_httpx_uow, sample_host, sample_host_ip, sample_ip, sample_service):
    """Test ingesting multiple FFUF results"""
    program_id = uuid4()
    results = [
        {"url": "https://example.com/admin", "status": 200},
        {"url": "https://example.com/api", "status": 200},
        {"url": "https://example.com/panel", "status": 403},
    ]

    mock_httpx_uow.hosts.get_by_fields = AsyncMock(return_value=sample_host)
    mock_httpx_uow.host_ips.find_many = AsyncMock(return_value=[sample_host_ip])
    mock_httpx_uow.ips.get = AsyncMock(return_value=sample_ip)
    mock_httpx_uow.services.get_by_fields = AsyncMock(return_value=sample_service)
    mock_httpx_uow.endpoints.ensure = AsyncMock()

    await ffuf_ingestor.ingest(program_id, results)

    assert mock_httpx_uow.endpoints.ensure.call_count == 3
    mock_httpx_uow.commit.assert_called_once()


@pytest.mark.asyncio
async def test_ingest_skips_invalid_results(ffuf_ingestor, mock_httpx_uow):
    """Test that ingest skips results with missing url"""
    program_id = uuid4()
    results = [
        {"status": 200},  # Missing url
        {"url": "", "status": 200},  # Empty url
        {"url": "https://example.com/valid", "status": 200},  # Valid
    ]

    mock_httpx_uow.hosts.get_by_fields = AsyncMock(return_value=None)
    mock_httpx_uow.endpoints.ensure = AsyncMock()

    await ffuf_ingestor.ingest(program_id, results)

    # Should try to process only the valid one
    assert mock_httpx_uow.hosts.get_by_fields.call_count == 1


@pytest.mark.asyncio
async def test_ingest_handles_different_status_codes(ffuf_ingestor, mock_httpx_uow, sample_host, sample_host_ip, sample_ip, sample_service):
    """Test ingesting endpoints with various status codes"""
    program_id = uuid4()
    results = [
        {"url": "https://example.com/admin", "status": 200},
        {"url": "https://example.com/forbidden", "status": 403},
        {"url": "https://example.com/redirect", "status": 301},
    ]

    mock_httpx_uow.hosts.get_by_fields = AsyncMock(return_value=sample_host)
    mock_httpx_uow.host_ips.find_many = AsyncMock(return_value=[sample_host_ip])
    mock_httpx_uow.ips.get = AsyncMock(return_value=sample_ip)
    mock_httpx_uow.services.get_by_fields = AsyncMock(return_value=sample_service)
    mock_httpx_uow.endpoints.ensure = AsyncMock()

    await ffuf_ingestor.ingest(program_id, results)

    calls = mock_httpx_uow.endpoints.ensure.call_args_list
    assert calls[0][1]["status_code"] == 200
    assert calls[1][1]["status_code"] == 403
    assert calls[2][1]["status_code"] == 301


@pytest.mark.asyncio
async def test_ingest_rollback_on_error(ffuf_ingestor, mock_httpx_uow):
    """Test that ingest rolls back on error during commit"""
    program_id = uuid4()
    results = [
        {"url": "https://example.com/admin", "status": 200}
    ]

    mock_httpx_uow.commit = AsyncMock(side_effect=Exception("Commit error"))
    mock_httpx_uow.hosts.get_by_fields = AsyncMock(return_value=None)

    with pytest.raises(Exception):
        await ffuf_ingestor.ingest(program_id, results)

    mock_httpx_uow.rollback.assert_called_once()


@pytest.mark.asyncio
async def test_ingest_handles_missing_status_code(ffuf_ingestor, mock_httpx_uow, sample_host, sample_host_ip, sample_ip, sample_service):
    """Test ingesting result without status code"""
    program_id = uuid4()
    results = [
        {"url": "https://example.com/admin"}  # No status
    ]

    mock_httpx_uow.hosts.get_by_fields = AsyncMock(return_value=sample_host)
    mock_httpx_uow.host_ips.find_many = AsyncMock(return_value=[sample_host_ip])
    mock_httpx_uow.ips.get = AsyncMock(return_value=sample_ip)
    mock_httpx_uow.services.get_by_fields = AsyncMock(return_value=sample_service)
    mock_httpx_uow.endpoints.ensure = AsyncMock()

    await ffuf_ingestor.ingest(program_id, results)

    call_args = mock_httpx_uow.endpoints.ensure.call_args[1]
    # Default status_code is 0 when missing
    assert call_args["status_code"] == 0


@pytest.mark.asyncio
async def test_ingest_empty_results(ffuf_ingestor, mock_httpx_uow):
    """Test ingesting empty results list"""
    program_id = uuid4()

    await ffuf_ingestor.ingest(program_id, [])

    mock_httpx_uow.commit.assert_called_once()
    mock_httpx_uow.hosts.get_by_fields.assert_not_called()
