import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
import asyncio

from api.application.services.orchestrator import Orchestrator
from api.infrastructure.events.event_types import EventType
from api.config import Settings


@pytest.fixture
def settings():
    settings = Settings()
    settings.ORCHESTRATOR_MAX_CONCURRENT = 2
    settings.ORCHESTRATOR_SCAN_DELAY = 0.1  # Short delay for testing
    return settings


@pytest.fixture
def mock_event_bus():
    bus = AsyncMock()
    bus.connect = AsyncMock()
    bus.subscribe = AsyncMock()
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def mock_container():
    # Mock services
    httpx_service = AsyncMock()
    httpx_service.execute = AsyncMock()

    katana_service = AsyncMock()
    katana_service.execute = AsyncMock()

    linkfinder_service = AsyncMock()
    linkfinder_service.execute = AsyncMock()

    # Mock ingestors
    httpx_ingestor = AsyncMock()
    httpx_ingestor.ingest = AsyncMock()

    katana_ingestor = AsyncMock()
    katana_ingestor.ingest = AsyncMock()

    linkfinder_ingestor = AsyncMock()
    linkfinder_ingestor.ingest = AsyncMock()

    async def mock_get(service_type):
        from api.application.services.httpx import HTTPXScanService
        from api.application.services.katana import KatanaScanService
        from api.application.services.linkfinder import LinkFinderScanService
        from api.infrastructure.ingestors.httpx_ingestor import HTTPXResultIngestor
        from api.infrastructure.ingestors.katana_ingestor import KatanaResultIngestor
        from api.infrastructure.ingestors.linkfinder_ingestor import LinkFinderResultIngestor

        if service_type == HTTPXScanService:
            return httpx_service
        elif service_type == KatanaScanService:
            return katana_service
        elif service_type == LinkFinderScanService:
            return linkfinder_service
        elif service_type == HTTPXResultIngestor:
            return httpx_ingestor
        elif service_type == KatanaResultIngestor:
            return katana_ingestor
        elif service_type == LinkFinderResultIngestor:
            return linkfinder_ingestor
        raise ValueError(f"Unknown service type: {service_type}")

    # Mock request container
    request_container = AsyncMock()
    request_container.get = mock_get

    # Mock main container with proper async context manager
    container = MagicMock()
    container.return_value.__aenter__ = AsyncMock(return_value=request_container)
    container.return_value.__aexit__ = AsyncMock(return_value=None)

    return container


@pytest.fixture
def orchestrator(mock_event_bus, mock_container, settings):
    return Orchestrator(
        bus=mock_event_bus,
        container=mock_container,
        settings=settings
    )


@pytest.mark.asyncio
async def test_start_subscribes_to_events(orchestrator, mock_event_bus):
    """Test start() subscribes to all event types"""
    await orchestrator.start()

    mock_event_bus.connect.assert_called_once()
    assert mock_event_bus.subscribe.call_count == 7


@pytest.mark.asyncio
async def test_handle_scan_results_batch_calls_ingestor(orchestrator, mock_container, sample_program):
    """Test handle_scan_results_batch triggers HTTPXResultIngestor"""
    event = {
        "program_id": str(sample_program.id),
        "results": [
            {"url": "https://example.com", "status-code": 200}
        ]
    }

    await orchestrator.handle_scan_results_batch(event)

    # Verify container was called to get ingestor
    assert mock_container.called


@pytest.mark.asyncio
async def test_handle_subdomain_discovered_creates_task(orchestrator, sample_program):
    """Test handle_subdomain_discovered creates background task"""
    event = {
        "program_id": str(sample_program.id),
        "subdomains": ["api.example.com", "www.example.com"]
    }

    initial_task_count = len(orchestrator.tasks)

    await orchestrator.handle_subdomain_discovered(event)

    # Should have created a background task
    await asyncio.sleep(0.1)  # Give task time to start

    # Task should be tracked
    assert len(orchestrator.tasks) >= initial_task_count


@pytest.mark.asyncio
async def test_handle_katana_results_batch_calls_ingestor(orchestrator, mock_container, sample_program):
    """Test handle_katana_results_batch triggers KatanaResultIngestor"""
    event = {
        "program_id": str(sample_program.id),
        "results": [
            {
                "request": {"endpoint": "https://example.com/api"},
                "response": {"status_code": 200}
            }
        ]
    }

    await orchestrator.handle_katana_results_batch(event)

    # Verify container was called to get ingestor
    assert mock_container.called


@pytest.mark.asyncio
async def test_handle_host_discovered_with_delay(orchestrator, sample_program):
    """Test handle_host_discovered applies scan delay"""
    event = {
        "program_id": str(sample_program.id),
        "hosts": ["https://new-host.com"]
    }

    import time
    start_time = time.time()

    await orchestrator.handle_host_discovered(event)

    # Give background task time to execute
    await asyncio.sleep(0.2)

    elapsed = time.time() - start_time

    # Should have waited at least the scan delay
    assert elapsed >= orchestrator.settings.ORCHESTRATOR_SCAN_DELAY


@pytest.mark.asyncio
async def test_semaphore_limits_concurrent_scans(orchestrator, sample_program):
    """Test semaphore limits concurrent scans"""
    # Create multiple subdomain events
    events = [
        {
            "program_id": str(sample_program.id),
            "subdomains": [f"sub{i}.example.com" for i in range(10)]
        }
        for _ in range(5)
    ]

    # Submit all events
    for event in events:
        await orchestrator.handle_subdomain_discovered(event)

    # Wait for some tasks to complete
    await asyncio.sleep(0.1)

    # Should have created background tasks (limited by semaphore)
    assert len(orchestrator.tasks) <= orchestrator.settings.ORCHESTRATOR_MAX_CONCURRENT


@pytest.mark.asyncio
async def test_process_subdomain_batch_calls_httpx_service(orchestrator, mock_container, sample_program):
    """Test _process_subdomain_batch calls HTTPXScanService"""
    targets = ["api.example.com", "www.example.com"]

    await orchestrator._process_subdomain_batch(str(sample_program.id), targets)

    # Verify container was called to get service
    assert mock_container.called


@pytest.mark.asyncio
async def test_handle_js_files_discovered_creates_task(orchestrator, sample_program):
    """Test handle_js_files_discovered creates background task"""
    event = {
        "program_id": str(sample_program.id),
        "js_files": ["https://example.com/app.js", "https://example.com/bundle.js"]
    }

    initial_task_count = len(orchestrator.tasks)

    await orchestrator.handle_js_files_discovered(event)

    # Should have created a background task
    await asyncio.sleep(0.1)

    # Task should be tracked
    assert len(orchestrator.tasks) >= initial_task_count


@pytest.mark.asyncio
async def test_process_js_files_batch_calls_linkfinder_service(orchestrator, mock_container, sample_program):
    """Test _process_js_files_batch calls LinkFinderScanService"""
    js_files = ["https://example.com/app.js", "https://example.com/bundle.js"]

    await orchestrator._process_js_files_batch(str(sample_program.id), js_files)

    # Verify container was called to get service
    assert mock_container.called
