import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from api.application.services.orchestrator import Orchestrator
from api.infrastructure.events.event_types import EventType


@pytest.fixture
def mock_bus():
    bus = AsyncMock()
    bus.publish = AsyncMock()
    bus.connect = AsyncMock()
    bus.subscribe = AsyncMock()
    return bus


@pytest.fixture
def mock_container():
    container = AsyncMock()

    async def mock_context_manager():
        mock_request_container = AsyncMock()
        return mock_request_container

    container.return_value = mock_context_manager()

    return container


@pytest.fixture
def mock_settings():
    settings = AsyncMock()
    settings.ORCHESTRATOR_MAX_CONCURRENT = 5
    settings.ORCHESTRATOR_SCAN_DELAY = 1
    return settings


@pytest.fixture
def orchestrator(mock_bus, mock_container, mock_settings):
    return Orchestrator(
        bus=mock_bus,
        container=mock_container,
        settings=mock_settings
    )


@pytest.mark.asyncio
async def test_subdomain_discovered_triggers_dnsx_basic(orchestrator, sample_program):
    """Test SUBDOMAIN_DISCOVERED event triggers DNSx Basic scan"""
    with patch.object(orchestrator, '_process_subdomain_batch', new_callable=AsyncMock) as mock_process:
        event = {
            "program_id": str(sample_program.id),
            "subdomains": ["example.com", "test.com"]
        }

        await orchestrator.handle_subdomain_discovered(event)

        # Wait for background task
        await orchestrator.tasks.pop()

        mock_process.assert_called_once_with(str(sample_program.id), ["example.com", "test.com"])


@pytest.mark.asyncio
async def test_dnsx_basic_results_filters_wildcard(orchestrator, mock_bus, sample_program):
    """Test DNSx Basic results handler filters wildcard and publishes DNSX_FILTERED_HOSTS"""
    mock_ingestor = AsyncMock()
    mock_container_instance = AsyncMock()
    mock_container_instance.get.return_value = mock_ingestor

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_container_instance)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    orchestrator.container = lambda: mock_cm

    event = {
        "program_id": str(sample_program.id),
        "results": [
            {"host": "real.example.com", "a": ["1.2.3.4"], "wildcard": False},
            {"host": "wildcard.example.com", "a": ["1.2.3.4"], "wildcard": True},
            {"host": "another.example.com", "a": ["5.6.7.8"], "wildcard": False}
        ]
    }

    await orchestrator.handle_dnsx_basic_results_batch(event)

    # Should ingest all results
    mock_ingestor.ingest.assert_called_once()

    # Should publish only non-wildcard hosts
    mock_bus.publish.assert_called_once()
    call_args = mock_bus.publish.call_args
    assert call_args[0][0] == EventType.DNSX_FILTERED_HOSTS
    assert len(call_args[0][1]["hosts"]) == 2
    assert "wildcard.example.com" not in call_args[0][1]["hosts"]


@pytest.mark.asyncio
async def test_dnsx_filtered_hosts_triggers_httpx(orchestrator, sample_program):
    """Test DNSX_FILTERED_HOSTS event triggers HTTPX scan"""
    with patch.object(orchestrator, '_process_filtered_hosts_batch', new_callable=AsyncMock) as mock_process:
        event = {
            "program_id": str(sample_program.id),
            "hosts": ["example.com", "test.com"]
        }

        await orchestrator.handle_dnsx_filtered_hosts(event)

        # Wait for background task
        await orchestrator.tasks.pop()

        mock_process.assert_called_once_with(str(sample_program.id), ["example.com", "test.com"])


@pytest.mark.asyncio
async def test_httpx_results_triggers_dnsx_deep(orchestrator, mock_bus, sample_program):
    """Test HTTPX results trigger DNSx Deep scan for live hosts"""
    mock_ingestor = AsyncMock()
    mock_container_instance = AsyncMock()
    mock_container_instance.get.return_value = mock_ingestor

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_container_instance)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    orchestrator.container = lambda: mock_cm

    event = {
        "program_id": str(sample_program.id),
        "results": [
            {"host": "example.com", "status_code": 200, "url": "https://example.com"},
            {"host": "test.com", "status_code": 404, "url": "https://test.com"},
            {"host": "example.com", "status_code": 301, "url": "https://example.com/page"}  # duplicate
        ]
    }

    await orchestrator.handle_scan_results_batch(event)

    # Should ingest results
    mock_ingestor.ingest.assert_called_once()

    # Should publish unique live hosts for DNSx Deep
    mock_bus.publish.assert_called_once()
    call_args = mock_bus.publish.call_args
    assert call_args[0][0] == EventType.HOST_DISCOVERED
    assert len(call_args[0][1]["hosts"]) == 2  # unique hosts
    assert call_args[0][1]["source"] == "httpx_for_dnsx_deep"


@pytest.mark.asyncio
async def test_host_discovered_with_dnsx_source_triggers_deep_scan(orchestrator, sample_program):
    """Test HOST_DISCOVERED with dnsx source triggers DNSx Deep"""
    with patch.object(orchestrator, '_process_dnsx_deep_batch', new_callable=AsyncMock) as mock_dnsx, \
         patch.object(orchestrator, '_process_host_batch', new_callable=AsyncMock) as mock_katana:

        event = {
            "program_id": str(sample_program.id),
            "hosts": ["example.com", "test.com"],
            "source": "httpx_for_dnsx_deep"
        }

        await orchestrator.handle_host_discovered(event)

        # Wait for background task
        await orchestrator.tasks.pop()

        # Should call DNSx Deep, not Katana
        mock_dnsx.assert_called_once_with(str(sample_program.id), ["example.com", "test.com"])
        mock_katana.assert_not_called()


@pytest.mark.asyncio
async def test_host_discovered_with_httpx_source_triggers_katana(orchestrator, sample_program):
    """Test HOST_DISCOVERED with httpx source triggers Katana (default behavior)"""
    with patch.object(orchestrator, '_process_dnsx_deep_batch', new_callable=AsyncMock) as mock_dnsx, \
         patch.object(orchestrator, '_process_host_batch', new_callable=AsyncMock) as mock_katana:

        event = {
            "program_id": str(sample_program.id),
            "hosts": ["example.com", "test.com"],
            "source": "httpx"
        }

        await orchestrator.handle_host_discovered(event)

        # Wait for background task
        await orchestrator.tasks.pop()

        # Should call Katana, not DNSx Deep
        mock_katana.assert_called_once_with(str(sample_program.id), ["example.com", "test.com"])
        mock_dnsx.assert_not_called()


@pytest.mark.asyncio
async def test_dnsx_deep_results_batch_ingests(orchestrator, sample_program):
    """Test DNSx Deep results are ingested"""
    mock_ingestor = AsyncMock()
    mock_container_instance = AsyncMock()
    mock_container_instance.get.return_value = mock_ingestor

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_container_instance)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    orchestrator.container = lambda: mock_cm

    event = {
        "program_id": str(sample_program.id),
        "results": [
            {
                "host": "example.com",
                "a": ["1.2.3.4"],
                "mx": ["mail.example.com"],
                "txt": ["v=spf1 ~all"],
                "ns": ["ns1.example.com"],
                "wildcard": False
            }
        ]
    }

    await orchestrator.handle_dnsx_deep_results_batch(event)

    mock_ingestor.ingest.assert_called_once_with(sample_program.id, event["results"])


@pytest.mark.asyncio
async def test_complete_dnsx_pipeline_flow(orchestrator, mock_bus, sample_program):
    """Test complete DNSx pipeline: Subfinder -> DNSx Basic -> HTTPX -> DNSx Deep"""
    events_published = []

    async def track_publish(event_type, data):
        events_published.append((event_type, data))

    mock_bus.publish.side_effect = track_publish

    mock_ingestor = AsyncMock()
    mock_dnsx_service = AsyncMock()
    mock_httpx_service = AsyncMock()

    mock_container_instance = AsyncMock()

    async def get_service(service_type):
        if "DNSxResultIngestor" in str(service_type):
            return mock_ingestor
        elif "DNSxScanService" in str(service_type):
            return mock_dnsx_service
        elif "HTTPXScanService" in str(service_type):
            return mock_httpx_service
        return AsyncMock()

    mock_container_instance.get.side_effect = get_service

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_container_instance)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    orchestrator.container = lambda: mock_cm

    # Step 1: DNSx Basic results with wildcard filtering
    await orchestrator.handle_dnsx_basic_results_batch({
        "program_id": str(sample_program.id),
        "results": [
            {"host": "real.example.com", "a": ["1.2.3.4"], "wildcard": False},
            {"host": "wildcard.example.com", "a": ["1.2.3.4"], "wildcard": True}
        ]
    })

    # Should publish DNSX_FILTERED_HOSTS with only non-wildcard
    assert any(e[0] == EventType.DNSX_FILTERED_HOSTS for e in events_published)
    filtered_event = next(e for e in events_published if e[0] == EventType.DNSX_FILTERED_HOSTS)
    assert len(filtered_event[1]["hosts"]) == 1
    assert "real.example.com" in filtered_event[1]["hosts"]

    # Step 2: HTTPX results trigger DNSx Deep
    events_published.clear()
    await orchestrator.handle_scan_results_batch({
        "program_id": str(sample_program.id),
        "results": [
            {"host": "real.example.com", "status_code": 200, "url": "https://real.example.com"}
        ]
    })

    # Should publish HOST_DISCOVERED for DNSx Deep
    assert any(e[0] == EventType.HOST_DISCOVERED for e in events_published)
    host_event = next(e for e in events_published if e[0] == EventType.HOST_DISCOVERED)
    assert host_event[1]["source"] == "httpx_for_dnsx_deep"
    assert "real.example.com" in host_event[1]["hosts"]


@pytest.mark.asyncio
async def test_dnsx_basic_no_results_skips_httpx(orchestrator, mock_bus, sample_program):
    """Test DNSx Basic with all wildcard results doesn't trigger HTTPX"""
    mock_ingestor = AsyncMock()
    mock_container_instance = AsyncMock()
    mock_container_instance.get.return_value = mock_ingestor

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_container_instance)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    orchestrator.container = lambda: mock_cm

    event = {
        "program_id": str(sample_program.id),
        "results": [
            {"host": "wildcard1.example.com", "a": ["1.2.3.4"], "wildcard": True},
            {"host": "wildcard2.example.com", "a": ["1.2.3.4"], "wildcard": True}
        ]
    }

    await orchestrator.handle_dnsx_basic_results_batch(event)

    # Should ingest but not publish DNSX_FILTERED_HOSTS
    mock_ingestor.ingest.assert_called_once()
    mock_bus.publish.assert_not_called()
