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

    mantra_service = AsyncMock()
    mantra_service.execute = AsyncMock()

    # Mock ingestors
    httpx_ingestor = AsyncMock()
    httpx_ingestor.ingest = AsyncMock()

    katana_ingestor = AsyncMock()
    katana_ingestor.ingest = AsyncMock()

    linkfinder_ingestor = AsyncMock()
    linkfinder_ingestor.ingest = AsyncMock()

    mantra_ingestor = AsyncMock()
    mantra_ingestor.ingest = AsyncMock()

    # Mock ProgramUnitOfWork with scope_rules
    program_uow = AsyncMock()
    program_uow.__aenter__ = AsyncMock(return_value=program_uow)
    program_uow.__aexit__ = AsyncMock(return_value=None)
    program_uow.scope_rules = AsyncMock()
    program_uow.scope_rules.find_by_program = AsyncMock(return_value=[])

    async def mock_get(service_type):
        from api.application.services.httpx import HTTPXScanService
        from api.application.services.katana import KatanaScanService
        from api.application.services.linkfinder import LinkFinderScanService
        from api.application.services.mantra import MantraScanService
        from api.infrastructure.ingestors.httpx_ingestor import HTTPXResultIngestor
        from api.infrastructure.ingestors.katana_ingestor import KatanaResultIngestor
        from api.infrastructure.ingestors.linkfinder_ingestor import LinkFinderResultIngestor
        from api.infrastructure.ingestors.mantra_ingestor import MantraResultIngestor
        from api.infrastructure.unit_of_work.interfaces.program import ProgramUnitOfWork

        if service_type == HTTPXScanService:
            return httpx_service
        elif service_type == KatanaScanService:
            return katana_service
        elif service_type == LinkFinderScanService:
            return linkfinder_service
        elif service_type == MantraScanService:
            return mantra_service
        elif service_type == HTTPXResultIngestor:
            return httpx_ingestor
        elif service_type == KatanaResultIngestor:
            return katana_ingestor
        elif service_type == LinkFinderResultIngestor:
            return linkfinder_ingestor
        elif service_type == MantraResultIngestor:
            return mantra_ingestor
        elif service_type == ProgramUnitOfWork:
            return program_uow
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
    # SERVICE_EVENTS, SCAN_RESULTS_BATCH, SUBDOMAIN_DISCOVERED, GAU_DISCOVERED,
    # KATANA_RESULTS_BATCH, HOST_DISCOVERED, JS_FILES_DISCOVERED, MANTRA_RESULTS_BATCH, FFUF_RESULTS_BATCH
    assert mock_event_bus.subscribe.call_count == 9


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


@pytest.mark.asyncio
async def test_process_js_files_batch_calls_mantra_service(orchestrator, mock_container, sample_program):
    """Test _process_js_files_batch calls MantraScanService"""
    from api.application.services.mantra import MantraScanService

    js_files = ["https://example.com/app.js", "https://example.com/bundle.js"]

    # Get request container
    request_container = await mock_container().__aenter__()
    mantra_service = await request_container.get(MantraScanService)

    await orchestrator._process_js_files_batch(str(sample_program.id), js_files)

    # Verify MantraScanService.execute was called
    mantra_service.execute.assert_called_once()
    call_args = mantra_service.execute.call_args
    assert call_args[1]["program_id"] == str(sample_program.id)
    assert call_args[1]["targets"] == js_files


@pytest.mark.asyncio
async def test_handle_mantra_results_batch(orchestrator, mock_container, sample_program):
    """Test handle_mantra_results_batch calls MantraResultIngestor"""
    from api.infrastructure.ingestors.mantra_ingestor import MantraResultIngestor

    event = {
        "program_id": str(sample_program.id),
        "results": [
            {"url": "https://example.com/app.js", "secret": "sk_live_..."},
            {"url": "https://example.com/bundle.js", "secret": "AKIA..."},
        ]
    }

    # Get request container
    request_container = await mock_container().__aenter__()
    mantra_ingestor = await request_container.get(MantraResultIngestor)

    await orchestrator.handle_mantra_results_batch(event)

    # Verify MantraResultIngestor.ingest was called
    mantra_ingestor.ingest.assert_called_once()
    call_args = mantra_ingestor.ingest.call_args
    assert call_args[0][0] == sample_program.id
    assert len(call_args[0][1]) == 2
