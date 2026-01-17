import pytest
from unittest.mock import AsyncMock
from uuid import uuid4

from api.infrastructure.ingestors.katana_ingestor import KatanaResultIngestor
from api.domain.models import HostModel, IPAddressModel, ServiceModel, EndpointModel, HostIPModel
from api.config import Settings


@pytest.fixture
def settings():
    return Settings()


@pytest.fixture
def mock_katana_uow():
    """Mock KatanaUnitOfWork with all required repositories"""
    uow = AsyncMock()

    uow.hosts = AsyncMock()
    uow.ips = AsyncMock()
    uow.host_ips = AsyncMock()
    uow.services = AsyncMock()
    uow.endpoints = AsyncMock()
    uow.input_parameters = AsyncMock()
    uow.headers = AsyncMock()

    uow.commit = AsyncMock()
    uow.rollback = AsyncMock()
    uow.create_savepoint = AsyncMock()
    uow.rollback_to_savepoint = AsyncMock()
    uow.release_savepoint = AsyncMock()

    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=None)

    return uow


@pytest.fixture
def mock_event_bus():
    """Mock EventBus"""
    bus = AsyncMock()
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def katana_ingestor(mock_katana_uow, settings):
    return KatanaResultIngestor(uow=mock_katana_uow, settings=settings)


@pytest.mark.asyncio
async def test_process_record_creates_endpoint(katana_ingestor, mock_katana_uow, sample_program, sample_host, sample_ip, sample_service):
    """Test _process_record creates endpoint from Katana result"""
    data = {
        "request": {
            "endpoint": "https://example.com/api/users?page=1",
            "method": "GET"
        },
        "response": {
            "status_code": 200,
            "headers": {"content-type": "application/json"}
        }
    }

    host_ip_model = HostIPModel(id=uuid4(), host_id=sample_host.id, ip_id=sample_ip.id, source="katana")
    endpoint = EndpointModel(
        id=uuid4(),
        host_id=sample_host.id,
        service_id=sample_service.id,
        path="/api/users",
        normalized_path="/api/users",
        methods=[]
    )

    mock_katana_uow.hosts.ensure = AsyncMock(return_value=sample_host)
    mock_katana_uow.host_ips.find_many = AsyncMock(return_value=[host_ip_model])
    mock_katana_uow.ips.get = AsyncMock(return_value=sample_ip)
    mock_katana_uow.services.get_by_fields = AsyncMock(return_value=sample_service)
    mock_katana_uow.endpoints.ensure = AsyncMock(return_value=endpoint)
    mock_katana_uow.input_parameters.ensure = AsyncMock()
    mock_katana_uow.headers.ensure = AsyncMock()

    await katana_ingestor._process_record(mock_katana_uow, sample_program.id, data)

    mock_katana_uow.hosts.ensure.assert_called_once_with(program_id=sample_program.id, host="example.com")
    mock_katana_uow.endpoints.ensure.assert_called_once()
    mock_katana_uow.input_parameters.ensure.assert_called_once()
    mock_katana_uow.headers.ensure.assert_called_once()


@pytest.mark.asyncio
async def test_process_record_handles_missing_endpoint(katana_ingestor, mock_katana_uow, sample_program):
    """Test _process_record skips records without endpoint URL"""
    data = {
        "request": {},
        "response": {}
    }

    await katana_ingestor._process_record(mock_katana_uow, sample_program.id, data)

    mock_katana_uow.hosts.ensure.assert_not_called()


@pytest.mark.asyncio
async def test_process_record_handles_missing_hostname(katana_ingestor, mock_katana_uow, sample_program):
    """Test _process_record skips records without hostname"""
    data = {
        "request": {
            "endpoint": "not-a-valid-url"
        },
        "response": {}
    }

    await katana_ingestor._process_record(mock_katana_uow, sample_program.id, data)

    # Should still try to ensure host but will get None hostname
    mock_katana_uow.hosts.ensure.assert_not_called()


@pytest.mark.asyncio
async def test_process_record_skips_if_no_host_ip_mapping(katana_ingestor, mock_katana_uow, sample_program, sample_host):
    """Test _process_record skips if host has no IP mapping"""
    data = {
        "request": {
            "endpoint": "https://example.com/api"
        },
        "response": {}
    }

    mock_katana_uow.hosts.ensure = AsyncMock(return_value=sample_host)
    mock_katana_uow.host_ips.find_many = AsyncMock(return_value=[])

    await katana_ingestor._process_record(mock_katana_uow, sample_program.id, data)

    mock_katana_uow.ips.get.assert_not_called()
    mock_katana_uow.services.get_by_fields.assert_not_called()


@pytest.mark.asyncio
async def test_process_record_skips_if_service_not_found(katana_ingestor, mock_katana_uow, sample_program, sample_host, sample_ip):
    """Test _process_record skips if service doesn't exist"""
    data = {
        "request": {
            "endpoint": "https://example.com/api"
        },
        "response": {}
    }

    host_ip_model = HostIPModel(id=uuid4(), host_id=sample_host.id, ip_id=sample_ip.id, source="katana")

    mock_katana_uow.hosts.ensure = AsyncMock(return_value=sample_host)
    mock_katana_uow.host_ips.find_many = AsyncMock(return_value=[host_ip_model])
    mock_katana_uow.ips.get = AsyncMock(return_value=sample_ip)
    mock_katana_uow.services.get_by_fields = AsyncMock(return_value=None)

    await katana_ingestor._process_record(mock_katana_uow, sample_program.id, data)

    mock_katana_uow.endpoints.ensure.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_endpoint_normalizes_path(katana_ingestor, mock_katana_uow, sample_host, sample_service):
    """Test _ensure_endpoint normalizes URL path"""
    request = {
        "endpoint": "https://example.com/api/users/123",
        "method": "POST"
    }
    response = {
        "status_code": 201
    }
    path = "/api/users/123"

    endpoint = EndpointModel(
        id=uuid4(),
        host_id=sample_host.id,
        service_id=sample_service.id,
        path=path,
        normalized_path="/api/users/{id}",
        methods=[]
    )

    mock_katana_uow.endpoints.ensure = AsyncMock(return_value=endpoint)

    result = await katana_ingestor._ensure_endpoint(mock_katana_uow, sample_host, sample_service, request, response, path)

    assert result == endpoint
    call_args = mock_katana_uow.endpoints.ensure.call_args[1]
    assert call_args["method"] == "POST"
    assert call_args["status_code"] == 201
    assert call_args["path"] == "/api/users/123"


@pytest.mark.asyncio
async def test_process_query_params_extracts_parameters(katana_ingestor, mock_katana_uow, sample_endpoint, sample_service):
    """Test _process_query_params extracts query parameters"""
    query_string = "q=search&page=2&limit=100"

    mock_katana_uow.input_parameters.ensure = AsyncMock()

    await katana_ingestor._process_query_params(mock_katana_uow, sample_endpoint, sample_service, query_string)

    assert mock_katana_uow.input_parameters.ensure.call_count == 3

    calls = mock_katana_uow.input_parameters.ensure.call_args_list
    param_names = [call[1]["name"] for call in calls]
    assert "q" in param_names
    assert "page" in param_names
    assert "limit" in param_names


@pytest.mark.asyncio
async def test_process_query_params_handles_empty_values(katana_ingestor, mock_katana_uow, sample_endpoint, sample_service):
    """Test _process_query_params handles parameters with empty values"""
    query_string = "flag&key="

    mock_katana_uow.input_parameters.ensure = AsyncMock()

    await katana_ingestor._process_query_params(mock_katana_uow, sample_endpoint, sample_service, query_string)

    assert mock_katana_uow.input_parameters.ensure.call_count == 2


@pytest.mark.asyncio
async def test_process_query_params_handles_no_query_string(katana_ingestor, mock_katana_uow, sample_endpoint, sample_service):
    """Test _process_query_params handles missing query string"""
    query_string = ""

    mock_katana_uow.input_parameters.ensure = AsyncMock()

    await katana_ingestor._process_query_params(mock_katana_uow, sample_endpoint, sample_service, query_string)

    mock_katana_uow.input_parameters.ensure.assert_not_called()


@pytest.mark.asyncio
async def test_process_headers_extracts_headers(katana_ingestor, mock_katana_uow, sample_endpoint):
    """Test _process_headers extracts response headers"""
    response = {
        "headers": {
            "Content-Type": "application/json",
            "X-Powered-By": "Express",
            "Cache-Control": "no-cache"
        }
    }

    mock_katana_uow.headers.ensure = AsyncMock()

    await katana_ingestor._process_headers(mock_katana_uow, sample_endpoint, response)

    assert mock_katana_uow.headers.ensure.call_count == 3

    calls = mock_katana_uow.headers.ensure.call_args_list
    header_names = [call[1]["name"] for call in calls]
    assert "content-type" in header_names
    assert "x-powered-by" in header_names
    assert "cache-control" in header_names


@pytest.mark.asyncio
async def test_process_headers_lowercases_names(katana_ingestor, mock_katana_uow, sample_endpoint):
    """Test _process_headers lowercases header names"""
    response = {
        "headers": {
            "Content-Type": "text/html"
        }
    }

    mock_katana_uow.headers.ensure = AsyncMock()

    await katana_ingestor._process_headers(mock_katana_uow, sample_endpoint, response)

    call_args = mock_katana_uow.headers.ensure.call_args[1]
    assert call_args["name"] == "content-type"


@pytest.mark.asyncio
async def test_process_headers_handles_missing_headers(katana_ingestor, mock_katana_uow, sample_endpoint):
    """Test _process_headers handles missing headers"""
    response = {}

    mock_katana_uow.headers.ensure = AsyncMock()

    await katana_ingestor._process_headers(mock_katana_uow, sample_endpoint, response)

    mock_katana_uow.headers.ensure.assert_not_called()


@pytest.mark.asyncio
async def test_process_headers_converts_values_to_string(katana_ingestor, mock_katana_uow, sample_endpoint):
    """Test _process_headers converts header values to strings"""
    response = {
        "headers": {
            "content-length": 1234
        }
    }

    mock_katana_uow.headers.ensure = AsyncMock()

    await katana_ingestor._process_headers(mock_katana_uow, sample_endpoint, response)

    call_args = mock_katana_uow.headers.ensure.call_args[1]
    assert call_args["value"] == "1234"
    assert isinstance(call_args["value"], str)


@pytest.mark.asyncio
async def test_is_js_file_detects_js_extension(katana_ingestor):
    """Test _is_js_file detects .js extension"""
    assert katana_ingestor._is_js_file("https://example.com/app.js") is True
    assert katana_ingestor._is_js_file("https://example.com/bundle.min.js") is True
    assert katana_ingestor._is_js_file("https://example.com/APP.JS") is True


@pytest.mark.asyncio
async def test_is_js_file_detects_js_with_query_params(katana_ingestor):
    """Test _is_js_file detects .js with query parameters"""
    assert katana_ingestor._is_js_file("https://example.com/app.js?v=123") is True
    assert katana_ingestor._is_js_file("https://example.com/bundle.js?t=456&v=1") is True


@pytest.mark.asyncio
async def test_is_js_file_rejects_non_js_files(katana_ingestor):
    """Test _is_js_file rejects non-JS files"""
    assert katana_ingestor._is_js_file("https://example.com/style.css") is False
    assert katana_ingestor._is_js_file("https://example.com/image.png") is False
    assert katana_ingestor._is_js_file("https://example.com/api/users") is False
    assert katana_ingestor._is_js_file("https://example.com/json") is False


