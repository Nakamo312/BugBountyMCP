import pytest
from unittest.mock import AsyncMock
from uuid import uuid4

from api.infrastructure.ingestors.linkfinder_ingestor import LinkFinderResultIngestor
from api.domain.models import HostModel, IPAddressModel, ServiceModel, EndpointModel, HostIPModel, ScopeRuleModel
from api.domain.enums import RuleType, ScopeAction
from api.config import Settings


@pytest.fixture
def settings():
    return Settings()


@pytest.fixture
def mock_linkfinder_uow():
    """Mock LinkFinderUnitOfWork with all required repositories"""
    uow = AsyncMock()

    uow.hosts = AsyncMock()
    uow.ips = AsyncMock()
    uow.host_ips = AsyncMock()
    uow.services = AsyncMock()
    uow.endpoints = AsyncMock()
    uow.input_parameters = AsyncMock()
    uow.scope_rules = AsyncMock()

    uow.commit = AsyncMock()
    uow.rollback = AsyncMock()

    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=None)

    return uow


@pytest.fixture
def linkfinder_ingestor(mock_linkfinder_uow, settings):
    return LinkFinderResultIngestor(uow=mock_linkfinder_uow, settings=settings)


@pytest.mark.asyncio
async def test_ingest_url_creates_endpoint(linkfinder_ingestor, mock_linkfinder_uow, sample_host, sample_ip, sample_service):
    """Test _ingest_url creates endpoint from discovered URL"""
    url = "https://example.com/api/users?page=1"

    endpoint = EndpointModel(
        id=uuid4(),
        host_id=sample_host.id,
        service_id=sample_service.id,
        path="/api/users",
        normalized_path="/api/users",
        methods=[]
    )

    mock_linkfinder_uow.services.ensure = AsyncMock(return_value=sample_service)
    mock_linkfinder_uow.endpoints.ensure = AsyncMock(return_value=endpoint)
    mock_linkfinder_uow.input_parameters.ensure = AsyncMock()

    await linkfinder_ingestor._ingest_url(url, sample_host, sample_ip)

    mock_linkfinder_uow.services.ensure.assert_called_once()
    mock_linkfinder_uow.endpoints.ensure.assert_called_once()
    mock_linkfinder_uow.input_parameters.ensure.assert_called_once()


@pytest.mark.asyncio
async def test_ingest_url_extracts_query_params(linkfinder_ingestor, mock_linkfinder_uow, sample_host, sample_ip, sample_service):
    """Test _ingest_url extracts query parameters"""
    url = "https://example.com/search?q=test&page=2&limit=50"

    endpoint = EndpointModel(
        id=uuid4(),
        host_id=sample_host.id,
        service_id=sample_service.id,
        path="/search",
        normalized_path="/search",
        methods=[]
    )

    mock_linkfinder_uow.services.ensure = AsyncMock(return_value=sample_service)
    mock_linkfinder_uow.endpoints.ensure = AsyncMock(return_value=endpoint)
    mock_linkfinder_uow.input_parameters.ensure = AsyncMock()

    await linkfinder_ingestor._ingest_url(url, sample_host, sample_ip)

    assert mock_linkfinder_uow.input_parameters.ensure.call_count == 3
    calls = mock_linkfinder_uow.input_parameters.ensure.call_args_list
    param_names = [call[1]["name"] for call in calls]
    assert "q" in param_names
    assert "page" in param_names
    assert "limit" in param_names


@pytest.mark.asyncio
async def test_ingest_url_handles_http_scheme(linkfinder_ingestor, mock_linkfinder_uow, sample_host, sample_ip):
    """Test _ingest_url handles http:// URLs"""
    url = "http://example.com/api"

    service = ServiceModel(id=uuid4(), ip_id=sample_ip.id, port=80, scheme="http")
    endpoint = EndpointModel(
        id=uuid4(),
        host_id=sample_host.id,
        service_id=service.id,
        path="/api",
        normalized_path="/api",
        methods=[]
    )

    mock_linkfinder_uow.services.ensure = AsyncMock(return_value=service)
    mock_linkfinder_uow.endpoints.ensure = AsyncMock(return_value=endpoint)
    mock_linkfinder_uow.input_parameters.ensure = AsyncMock()

    await linkfinder_ingestor._ingest_url(url, sample_host, sample_ip)

    call_args = mock_linkfinder_uow.services.ensure.call_args[1]
    assert call_args["scheme"] == "http"
    assert call_args["port"] == 80


@pytest.mark.asyncio
async def test_ingest_url_handles_custom_port(linkfinder_ingestor, mock_linkfinder_uow, sample_host, sample_ip):
    """Test _ingest_url handles custom ports"""
    url = "https://example.com:8443/api"

    service = ServiceModel(id=uuid4(), ip_id=sample_ip.id, port=8443, scheme="https")
    endpoint = EndpointModel(
        id=uuid4(),
        host_id=sample_host.id,
        service_id=service.id,
        path="/api",
        normalized_path="/api",
        methods=[]
    )

    mock_linkfinder_uow.services.ensure = AsyncMock(return_value=service)
    mock_linkfinder_uow.endpoints.ensure = AsyncMock(return_value=endpoint)
    mock_linkfinder_uow.input_parameters.ensure = AsyncMock()

    await linkfinder_ingestor._ingest_url(url, sample_host, sample_ip)

    call_args = mock_linkfinder_uow.services.ensure.call_args[1]
    assert call_args["port"] == 8443


@pytest.mark.asyncio
async def test_is_in_scope_domain_match(linkfinder_ingestor):
    """Test _is_in_scope matches domain rules"""
    scope_rules = [
        ScopeRuleModel(
            id=uuid4(),
            program_id=uuid4(),
            action=ScopeAction.INCLUDE,
            rule_type=RuleType.DOMAIN,
            pattern="example.com"
        )
    ]

    assert linkfinder_ingestor._is_in_scope("https://example.com/api", scope_rules) is True
    assert linkfinder_ingestor._is_in_scope("https://api.example.com/users", scope_rules) is True
    assert linkfinder_ingestor._is_in_scope("https://other.com/api", scope_rules) is False


@pytest.mark.asyncio
async def test_is_in_scope_regex_match(linkfinder_ingestor):
    """Test _is_in_scope matches regex rules"""
    scope_rules = [
        ScopeRuleModel(
            id=uuid4(),
            program_id=uuid4(),
            action=ScopeAction.INCLUDE,
            rule_type=RuleType.REGEX,
            pattern=r"https://.*\.example\.com/.*"
        )
    ]

    assert linkfinder_ingestor._is_in_scope("https://api.example.com/users", scope_rules) is True
    assert linkfinder_ingestor._is_in_scope("https://www.example.com/index", scope_rules) is True
    assert linkfinder_ingestor._is_in_scope("https://example.com/api", scope_rules) is False


@pytest.mark.asyncio
async def test_is_in_scope_no_rules_allows_all(linkfinder_ingestor):
    """Test _is_in_scope allows all URLs when no rules defined"""
    scope_rules = []

    assert linkfinder_ingestor._is_in_scope("https://example.com/api", scope_rules) is True
    assert linkfinder_ingestor._is_in_scope("https://anything.com/path", scope_rules) is True


@pytest.mark.asyncio
async def test_is_in_scope_invalid_url(linkfinder_ingestor):
    """Test _is_in_scope rejects invalid URLs"""
    scope_rules = [
        ScopeRuleModel(
            id=uuid4(),
            program_id=uuid4(),
            action=ScopeAction.INCLUDE,
            rule_type=RuleType.DOMAIN,
            pattern="example.com"
        )
    ]

    assert linkfinder_ingestor._is_in_scope("not-a-valid-url", scope_rules) is False
    assert linkfinder_ingestor._is_in_scope("/relative/path", scope_rules) is False


@pytest.mark.asyncio
async def test_ingest_filters_out_of_scope_urls(linkfinder_ingestor, mock_linkfinder_uow, sample_program, sample_host, sample_ip):
    """Test ingest filters URLs not matching scope"""
    result = {
        "source_js": "https://example.com/app.js",
        "urls": [
            "https://example.com/api/users",
            "https://external.com/data",
            "https://api.example.com/products"
        ],
        "host": "example.com"
    }

    scope_rules = [
        ScopeRuleModel(
            id=sample_program.id,
            program_id=sample_program.id,
            action=ScopeAction.INCLUDE,
            rule_type=RuleType.DOMAIN,
            pattern="example.com"
        )
    ]

    host_ip_model = HostIPModel(id=uuid4(), host_id=sample_host.id, ip_id=sample_ip.id, source="linkfinder")

    mock_linkfinder_uow.scope_rules.find_by_program = AsyncMock(return_value=scope_rules)
    mock_linkfinder_uow.hosts.ensure = AsyncMock(return_value=sample_host)
    mock_linkfinder_uow.host_ips.find_many = AsyncMock(return_value=[host_ip_model])
    mock_linkfinder_uow.ips.get = AsyncMock(return_value=sample_ip)
    mock_linkfinder_uow.services.ensure = AsyncMock()
    mock_linkfinder_uow.endpoints.ensure = AsyncMock()
    mock_linkfinder_uow.input_parameters.ensure = AsyncMock()

    await linkfinder_ingestor.ingest(sample_program.id, result)

    # Should only ingest 2 URLs (example.com and api.example.com), external.com filtered out
    assert mock_linkfinder_uow.endpoints.ensure.call_count == 2


@pytest.mark.asyncio
async def test_ingest_handles_missing_host(linkfinder_ingestor, mock_linkfinder_uow, sample_program):
    """Test ingest skips results without host"""
    result = {
        "source_js": "https://example.com/app.js",
        "urls": ["https://example.com/api"]
    }

    mock_linkfinder_uow.scope_rules.find_by_program = AsyncMock(return_value=[])

    await linkfinder_ingestor.ingest(sample_program.id, result)

    mock_linkfinder_uow.hosts.ensure.assert_not_called()


@pytest.mark.asyncio
async def test_ingest_handles_missing_urls(linkfinder_ingestor, mock_linkfinder_uow, sample_program):
    """Test ingest skips results without URLs"""
    result = {
        "source_js": "https://example.com/app.js",
        "host": "example.com"
    }

    mock_linkfinder_uow.scope_rules.find_by_program = AsyncMock(return_value=[])

    await linkfinder_ingestor.ingest(sample_program.id, result)

    mock_linkfinder_uow.hosts.ensure.assert_not_called()


@pytest.mark.asyncio
async def test_ingest_skips_if_no_host_ip_mapping(linkfinder_ingestor, mock_linkfinder_uow, sample_program, sample_host):
    """Test ingest skips if host has no IP mapping"""
    result = {
        "source_js": "https://example.com/app.js",
        "urls": ["https://example.com/api"],
        "host": "example.com"
    }

    mock_linkfinder_uow.scope_rules.find_by_program = AsyncMock(return_value=[])
    mock_linkfinder_uow.hosts.ensure = AsyncMock(return_value=sample_host)
    mock_linkfinder_uow.host_ips.find_many = AsyncMock(return_value=[])

    await linkfinder_ingestor.ingest(sample_program.id, result)

    mock_linkfinder_uow.ips.get.assert_not_called()
    mock_linkfinder_uow.endpoints.ensure.assert_not_called()


@pytest.mark.asyncio
async def test_ingest_commits_transaction(linkfinder_ingestor, mock_linkfinder_uow, sample_program, sample_host, sample_ip):
    """Test ingest commits transaction after processing"""
    result = {
        "source_js": "https://example.com/app.js",
        "urls": ["https://example.com/api"],
        "host": "example.com"
    }

    host_ip_model = HostIPModel(id=uuid4(), host_id=sample_host.id, ip_id=sample_ip.id, source="linkfinder")

    mock_linkfinder_uow.scope_rules.find_by_program = AsyncMock(return_value=[])
    mock_linkfinder_uow.hosts.ensure = AsyncMock(return_value=sample_host)
    mock_linkfinder_uow.host_ips.find_many = AsyncMock(return_value=[host_ip_model])
    mock_linkfinder_uow.ips.get = AsyncMock(return_value=sample_ip)
    mock_linkfinder_uow.services.ensure = AsyncMock()
    mock_linkfinder_uow.endpoints.ensure = AsyncMock()
    mock_linkfinder_uow.input_parameters.ensure = AsyncMock()

    await linkfinder_ingestor.ingest(sample_program.id, result)

    mock_linkfinder_uow.commit.assert_called_once()


@pytest.mark.asyncio
async def test_ingest_rollback_on_error(linkfinder_ingestor, mock_linkfinder_uow, sample_program):
    """Test ingest rolls back transaction on error"""
    result = {
        "source_js": "https://example.com/app.js",
        "urls": ["https://example.com/api"],
        "host": "example.com"
    }

    mock_linkfinder_uow.scope_rules.find_by_program = AsyncMock(side_effect=Exception("Database error"))

    with pytest.raises(Exception):
        await linkfinder_ingestor.ingest(sample_program.id, result)

    mock_linkfinder_uow.rollback.assert_called_once()
