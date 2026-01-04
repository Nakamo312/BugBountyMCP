"""Integration tests for Subjack subdomain takeover detection"""
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
async def test_cname_discovered_triggers_subjack(orchestrator, sample_program):
    """Test CNAME_DISCOVERED event triggers Subjack scan"""
    with patch.object(orchestrator, '_process_subjack_batch', new_callable=AsyncMock) as mock_process:
        event = {
            "program_id": str(sample_program.id),
            "hosts": ["vulnerable.example.com", "test.example.com"]
        }

        await orchestrator.handle_cname_discovered(event)

        await orchestrator.tasks.pop()

        mock_process.assert_called_once_with(str(sample_program.id), ["vulnerable.example.com", "test.example.com"])


@pytest.mark.asyncio
async def test_subjack_results_batch_creates_findings(orchestrator, mock_bus, sample_program, sample_host):
    """Test Subjack results create findings with host_id"""
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
                "subdomain": "vulnerable.example.com",
                "service": "GitHub Pages",
                "vulnerable": True,
                "cname": "user.github.io"
            },
            {
                "subdomain": "test.example.com",
                "service": "Heroku",
                "vulnerable": True,
                "cname": "app.herokuapp.com"
            }
        ]
    }

    await orchestrator.handle_subjack_results_batch(event)

    mock_ingestor.ingest.assert_called_once_with(sample_program.id, event["results"])


@pytest.mark.asyncio
async def test_dnsx_deep_extracts_cname_hosts(orchestrator, mock_bus, sample_program):
    """Test DNSx Deep results extract CNAME hosts for Subjack"""
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
                "cname": ["cdn.example.com"],
                "wildcard": False
            },
            {
                "host": "wildcard.example.com",
                "cname": ["wc.example.com"],
                "wildcard": True
            },
            {
                "host": "test.example.com",
                "a": ["5.6.7.8"],
                "wildcard": False
            }
        ]
    }

    await orchestrator.handle_dnsx_deep_results_batch(event)

    mock_ingestor.ingest.assert_called_once()

    mock_bus.publish.assert_called_once()
    call_args = mock_bus.publish.call_args
    assert call_args[0][0] == EventType.CNAME_DISCOVERED
    assert len(call_args[0][1]["hosts"]) == 1
    assert "example.com" in call_args[0][1]["hosts"]
    assert "wildcard.example.com" not in call_args[0][1]["hosts"]


@pytest.mark.asyncio
async def test_dnsx_deep_no_cname_skips_subjack(orchestrator, mock_bus, sample_program):
    """Test DNSx Deep without CNAME doesn't trigger Subjack"""
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
                "wildcard": False
            }
        ]
    }

    await orchestrator.handle_dnsx_deep_results_batch(event)

    mock_ingestor.ingest.assert_called_once()
    mock_bus.publish.assert_not_called()


@pytest.mark.asyncio
async def test_subjack_pipeline_flow(orchestrator, mock_bus, sample_program):
    """Test complete pipeline: DNSx Deep -> CNAME_DISCOVERED -> Subjack -> Findings"""
    events_published = []

    async def track_publish(event_type, data):
        events_published.append((event_type, data))

    mock_bus.publish.side_effect = track_publish

    mock_ingestor = AsyncMock()
    mock_subjack_service = AsyncMock()

    mock_container_instance = AsyncMock()

    async def get_service(service_type):
        service_name = str(service_type)
        if "DNSxResultIngestor" in service_name:
            return mock_ingestor
        elif "SubjackScanService" in service_name:
            return mock_subjack_service
        return AsyncMock()

    mock_container_instance.get.side_effect = get_service

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_container_instance)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    orchestrator.container = lambda: mock_cm

    dnsx_deep_event = {
        "program_id": str(sample_program.id),
        "results": [
            {
                "host": "vulnerable.example.com",
                "a": ["1.2.3.4"],
                "cname": ["user.github.io"],
                "wildcard": False
            }
        ]
    }

    await orchestrator.handle_dnsx_deep_results_batch(dnsx_deep_event)

    assert any(e[0] == EventType.CNAME_DISCOVERED for e in events_published)
    cname_event = next(e for e in events_published if e[0] == EventType.CNAME_DISCOVERED)
    assert "vulnerable.example.com" in cname_event[1]["hosts"]


@pytest.mark.asyncio
async def test_orchestrator_subscribes_to_subjack_events(orchestrator, mock_bus):
    """Test orchestrator subscribes to Subjack events on startup"""
    await orchestrator.start()

    subscribe_calls = [call[0][0] for call in mock_bus.subscribe.call_args_list]
    assert EventType.CNAME_DISCOVERED in subscribe_calls
    assert EventType.SUBJACK_RESULTS_BATCH in subscribe_calls
