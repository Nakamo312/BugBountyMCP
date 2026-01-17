import pytest
from unittest.mock import AsyncMock, call
from uuid import uuid4

from api.infrastructure.ingestors.httpx_ingestor import HTTPXResultIngestor
from api.domain.models import HostModel, IPAddressModel, ServiceModel, EndpointModel, InputParameterModel, HostIPModel
from api.config import Settings


@pytest.fixture
def settings():
    return Settings()


@pytest.fixture
def mock_event_bus():
    bus = AsyncMock()
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def httpx_ingestor(mock_uow, settings):
    mock_uow.hosts.get_by_fields = AsyncMock(return_value=None)
    mock_uow.scope_rules = AsyncMock()
    mock_uow.scope_rules.find_by_program = AsyncMock(return_value=[])
    return HTTPXResultIngestor(uow=mock_uow, settings=settings)


@pytest.mark.asyncio
async def test_ensure_host_creates_host(httpx_ingestor, mock_uow, sample_program):
    """Test _ensure_host creates host"""
    data = {"host": "example.com"}
    host = HostModel(id=uuid4(), host="example.com", program_id=sample_program.id)

    mock_uow.hosts.ensure = AsyncMock(return_value=host)

    result = await httpx_ingestor._ensure_host(mock_uow, sample_program.id, data)

    assert result == host
    mock_uow.hosts.ensure.assert_called_once_with(program_id=sample_program.id, host="example.com", in_scope=True)


@pytest.mark.asyncio
async def test_ensure_host_handles_missing_host(httpx_ingestor, mock_uow, sample_program):
    """Test _ensure_host returns None when host missing"""
    data = {}

    result = await httpx_ingestor._ensure_host(mock_uow, sample_program.id, data)

    assert result is None


@pytest.mark.asyncio
async def test_ensure_ip_creates_ip_and_mapping(httpx_ingestor, mock_uow, sample_program, sample_host):
    """Test _ensure_ip creates IP and host-IP mapping"""
    data = {"host_ip": "1.2.3.4"}
    ip = IPAddressModel(id=uuid4(), address="1.2.3.4", program_id=sample_program.id)

    mock_uow.ips.ensure = AsyncMock(return_value=ip)
    mock_uow.host_ips.ensure = AsyncMock()

    result = await httpx_ingestor._ensure_ip(mock_uow, sample_program.id, sample_host, data)

    assert result == ip
    mock_uow.ips.ensure.assert_called_once_with(program_id=sample_program.id, address="1.2.3.4")
    mock_uow.host_ips.ensure.assert_called_once_with(host_id=sample_host.id, ip_id=ip.id, source="httpx")


@pytest.mark.asyncio
async def test_ensure_ip_handles_dns_records(httpx_ingestor, mock_uow, sample_program, sample_host):
    """Test _ensure_ip processes DNS A records"""
    data = {"host_ip": "1.2.3.4", "a": ["5.6.7.8", "9.10.11.12"]}
    ip1 = IPAddressModel(id=uuid4(), address="1.2.3.4", program_id=sample_program.id)
    ip2 = IPAddressModel(id=uuid4(), address="5.6.7.8", program_id=sample_program.id)
    ip3 = IPAddressModel(id=uuid4(), address="9.10.11.12", program_id=sample_program.id)

    mock_uow.ips.ensure = AsyncMock(side_effect=[ip1, ip2, ip3])
    mock_uow.host_ips.ensure = AsyncMock()

    result = await httpx_ingestor._ensure_ip(mock_uow, sample_program.id, sample_host, data)

    assert result == ip1
    assert mock_uow.ips.ensure.call_count == 3
    assert mock_uow.host_ips.ensure.call_count == 3


@pytest.mark.asyncio
async def test_ensure_service_creates_service(httpx_ingestor, mock_uow, sample_ip):
    """Test _ensure_service creates service"""
    data = {"scheme": "https", "port": 443, "tech": ["nginx", "php"]}
    service = ServiceModel(id=uuid4(), ip_id=sample_ip.id, port=443, scheme="https")

    mock_uow.services.ensure = AsyncMock(return_value=service)

    result = await httpx_ingestor._ensure_service(mock_uow, sample_ip, data)

    assert result == service
    mock_uow.services.ensure.assert_called_once()
    call_args = mock_uow.services.ensure.call_args[1]
    assert call_args["scheme"] == "https"
    assert call_args["port"] == 443
    assert call_args["technologies"] == {"nginx": True, "php": True}


@pytest.mark.asyncio
async def test_ensure_endpoint_creates_endpoint(httpx_ingestor, mock_uow, sample_host, sample_service):
    """Test _ensure_endpoint creates endpoint with normalized path"""
    data = {"host": "example.com", "scheme": "https", "path": "/api/users/123", "method": "GET", "status_code": 200}
    endpoint = EndpointModel(
        id=uuid4(),
        host_id=sample_host.id,
        service_id=sample_service.id,
        path="/api/users/123",
        normalized_path="/api/users/{id}",
        methods=[]
    )

    mock_uow.endpoints.ensure = AsyncMock(return_value=endpoint)

    result = await httpx_ingestor._ensure_endpoint(mock_uow, sample_host, sample_service, data)

    assert result == endpoint
    mock_uow.endpoints.ensure.assert_called_once()
    call_args = mock_uow.endpoints.ensure.call_args[1]
    assert call_args["path"] == "/api/users/123"
    assert call_args["method"] == "GET"
    assert call_args["status_code"] == 200


@pytest.mark.asyncio
async def test_process_query_params_extracts_parameters(httpx_ingestor, mock_uow, sample_endpoint, sample_service):
    """Test _process_query_params extracts query parameters"""
    data = {"path": "/search?q=test&page=1&limit=50"}

    mock_uow.input_parameters.ensure = AsyncMock()

    await httpx_ingestor._process_query_params(mock_uow, sample_endpoint, sample_service, data)

    assert mock_uow.input_parameters.ensure.call_count == 3
    calls = mock_uow.input_parameters.ensure.call_args_list

    # Check all parameters were processed
    param_names = [call[1]["name"] for call in calls]
    assert "q" in param_names
    assert "page" in param_names
    assert "limit" in param_names


@pytest.mark.asyncio
async def test_process_query_params_handles_no_value(httpx_ingestor, mock_uow, sample_endpoint, sample_service):
    """Test _process_query_params handles parameters without values"""
    data = {"path": "/api?flag"}

    mock_uow.input_parameters.ensure = AsyncMock()

    await httpx_ingestor._process_query_params(mock_uow, sample_endpoint, sample_service, data)

    assert mock_uow.input_parameters.ensure.call_count == 1
    call_args = mock_uow.input_parameters.ensure.call_args[1]
    assert call_args["name"] == "flag"
    assert call_args["example_value"] == ""


@pytest.mark.asyncio
async def test_process_record_returns_new_host_url(httpx_ingestor, mock_uow, sample_program):
    """Test _process_record returns URL for new host with active service"""
    data = {
        "host": "new-host.com",
        "host_ip": "1.2.3.4",
        "scheme": "https",
        "port": 443,
        "path": "/",
        "status_code": 200
    }

    host = HostModel(id=uuid4(), host="new-host.com", program_id=sample_program.id)
    ip = IPAddressModel(id=uuid4(), address="1.2.3.4", program_id=sample_program.id)
    service = ServiceModel(id=uuid4(), ip_id=ip.id, port=443, scheme="https")
    endpoint = EndpointModel(id=uuid4(), host_id=host.id, service_id=service.id, path="/", normalized_path="/", methods=[])

    mock_uow.hosts.get_by_fields = AsyncMock(return_value=None)
    mock_uow.hosts.ensure = AsyncMock(return_value=host)
    mock_uow.ips.ensure = AsyncMock(return_value=ip)
    mock_uow.host_ips.ensure = AsyncMock()
    mock_uow.services.ensure = AsyncMock(return_value=service)
    mock_uow.endpoints.ensure = AsyncMock(return_value=endpoint)
    mock_uow.input_parameters.ensure = AsyncMock()

    seen_hosts = set()
    host_url, is_new = await httpx_ingestor._process_record(mock_uow, sample_program.id, data, seen_hosts)

    assert host_url == "https://new-host.com"
    assert is_new is True
    assert "new-host.com" in seen_hosts


@pytest.mark.asyncio
async def test_process_record_includes_non_standard_port(httpx_ingestor, mock_uow, sample_program):
    """Test _process_record includes port in URL for non-standard ports"""
    data = {
        "host": "api.example.com",
        "host_ip": "1.2.3.4",
        "scheme": "https",
        "port": 8443,
        "path": "/",
        "status_code": 200
    }

    host = HostModel(id=uuid4(), host="api.example.com", program_id=sample_program.id)
    ip = IPAddressModel(id=uuid4(), address="1.2.3.4", program_id=sample_program.id)
    service = ServiceModel(id=uuid4(), ip_id=ip.id, port=8443, scheme="https")
    endpoint = EndpointModel(id=uuid4(), host_id=host.id, service_id=service.id, path="/", normalized_path="/", methods=[])

    mock_uow.hosts.get_by_fields = AsyncMock(return_value=None)
    mock_uow.hosts.ensure = AsyncMock(return_value=host)
    mock_uow.ips.ensure = AsyncMock(return_value=ip)
    mock_uow.host_ips.ensure = AsyncMock()
    mock_uow.services.ensure = AsyncMock(return_value=service)
    mock_uow.endpoints.ensure = AsyncMock(return_value=endpoint)
    mock_uow.input_parameters.ensure = AsyncMock()

    seen_hosts = set()
    host_url, is_new = await httpx_ingestor._process_record(mock_uow, sample_program.id, data, seen_hosts)

    assert host_url == "https://api.example.com:8443"
    assert is_new is True


@pytest.mark.asyncio
async def test_process_record_skips_existing_host(httpx_ingestor, mock_uow, sample_program, sample_host):
    """Test _process_record skips already seen hosts"""
    data = {
        "host": "example.com",
        "host_ip": "1.2.3.4",
        "scheme": "https",
        "port": 443,
        "path": "/api",
        "status_code": 200
    }

    ip = IPAddressModel(id=uuid4(), address="1.2.3.4", program_id=sample_program.id)
    service = ServiceModel(id=uuid4(), ip_id=ip.id, port=443, scheme="https")
    endpoint = EndpointModel(id=uuid4(), host_id=sample_host.id, service_id=service.id, path="/api", normalized_path="/api", methods=[])

    mock_uow.hosts.get_by_fields = AsyncMock(return_value=sample_host)
    mock_uow.hosts.ensure = AsyncMock(return_value=sample_host)
    mock_uow.ips.ensure = AsyncMock(return_value=ip)
    mock_uow.host_ips.ensure = AsyncMock()
    mock_uow.services.ensure = AsyncMock(return_value=service)
    mock_uow.endpoints.ensure = AsyncMock(return_value=endpoint)
    mock_uow.input_parameters.ensure = AsyncMock()

    seen_hosts = set()
    host_url, is_new = await httpx_ingestor._process_record(mock_uow, sample_program.id, data, seen_hosts)

    assert host_url is None
    assert is_new is False


@pytest.mark.asyncio
async def test_is_js_file_detects_js_extension(httpx_ingestor):
    """Test _is_js_file detects .js extension"""
    assert httpx_ingestor._is_js_file("https://example.com/app.js") is True
    assert httpx_ingestor._is_js_file("https://example.com/bundle.min.js") is True
    assert httpx_ingestor._is_js_file("https://example.com/APP.JS") is True


@pytest.mark.asyncio
async def test_is_js_file_detects_js_with_query_params(httpx_ingestor):
    """Test _is_js_file detects .js with query parameters"""
    assert httpx_ingestor._is_js_file("https://example.com/app.js?v=123") is True
    assert httpx_ingestor._is_js_file("https://example.com/bundle.js?t=456&v=1") is True


@pytest.mark.asyncio
async def test_is_js_file_rejects_non_js_files(httpx_ingestor):
    """Test _is_js_file rejects non-JS files"""
    assert httpx_ingestor._is_js_file("https://example.com/style.css") is False
    assert httpx_ingestor._is_js_file("https://example.com/image.png") is False
    assert httpx_ingestor._is_js_file("https://example.com/api/users") is False


@pytest.mark.asyncio
async def test_process_batch_publishes_live_js_files(httpx_ingestor, mock_uow, mock_event_bus, sample_program, sample_host, sample_ip, sample_service):
    """Test _process_batch collects live JS files with status 200"""
    host_ip_model = HostIPModel(id=uuid4(), host_id=sample_host.id, ip_id=sample_ip.id, source="httpx")
    endpoint = EndpointModel(
        id=uuid4(),
        host_id=sample_host.id,
        service_id=sample_service.id,
        path="/app.js",
        normalized_path="/app.js",
        methods=[]
    )

    mock_uow.hosts.get_by_fields = AsyncMock(return_value=None)
    mock_uow.hosts.ensure = AsyncMock(return_value=sample_host)
    mock_uow.ips.ensure = AsyncMock(return_value=sample_ip)
    mock_uow.host_ips.ensure = AsyncMock(return_value=host_ip_model)
    mock_uow.services.ensure = AsyncMock(return_value=sample_service)
    mock_uow.endpoints.ensure = AsyncMock(return_value=endpoint)
    mock_uow.input_parameters.ensure = AsyncMock()

    batch = [
        {"host": "example.com", "url": "https://example.com/app.js", "status_code": 200, "host_ip": "1.2.3.4", "scheme": "https", "port": 443, "path": "/app.js"},
        {"host": "example.com", "url": "https://example.com/bundle.js", "status_code": 200, "host_ip": "1.2.3.4", "scheme": "https", "port": 443, "path": "/bundle.js"},
        {"host": "example.com", "url": "https://example.com/dead.js", "status_code": 404, "host_ip": "1.2.3.4", "scheme": "https", "port": 443, "path": "/dead.js"},
        {"host": "example.com", "url": "https://example.com/api/users", "status_code": 200, "host_ip": "1.2.3.4", "scheme": "https", "port": 443, "path": "/api/users"},
    ]

    await httpx_ingestor._process_batch(mock_uow, sample_program.id, batch)

    # Check that JS files were collected (2 live JS files)
    assert len(httpx_ingestor._js_files) == 2
    assert "https://example.com/app.js" in httpx_ingestor._js_files
    assert "https://example.com/bundle.js" in httpx_ingestor._js_files


@pytest.mark.asyncio
async def test_ingest_returns_js_files_in_result(httpx_ingestor, mock_uow, sample_program, sample_host, sample_ip, sample_service):
    """Test ingest returns discovered JS files in IngestResult"""
    endpoint = EndpointModel(id=uuid4(), host_id=sample_host.id, service_id=sample_service.id, path="/", normalized_path="/", methods=[])

    mock_uow.hosts.get_by_fields = AsyncMock(return_value=None)
    mock_uow.hosts.ensure = AsyncMock(return_value=sample_host)
    mock_uow.ips.ensure = AsyncMock(return_value=sample_ip)
    mock_uow.host_ips.ensure = AsyncMock()
    mock_uow.services.ensure = AsyncMock(return_value=sample_service)
    mock_uow.endpoints.ensure = AsyncMock(return_value=endpoint)
    mock_uow.input_parameters.ensure = AsyncMock()
    mock_uow.commit = AsyncMock()
    mock_uow.create_savepoint = AsyncMock()
    mock_uow.release_savepoint = AsyncMock()
    mock_uow.scope_rules.find_by_program = AsyncMock(return_value=[])
    mock_uow.__aenter__ = AsyncMock(return_value=mock_uow)
    mock_uow.__aexit__ = AsyncMock(return_value=None)

    results = [
        {"host": "example.com", "url": "https://example.com/app.js", "status_code": 200, "host_ip": "1.2.3.4", "scheme": "https", "port": 443, "path": "/app.js"},
    ]

    ingest_result = await httpx_ingestor.ingest(sample_program.id, results)

    # Check that JS files are returned in IngestResult
    assert "https://example.com/app.js" in ingest_result.js_files
