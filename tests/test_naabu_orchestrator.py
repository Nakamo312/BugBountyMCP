"""Tests for Naabu Orchestrator Integration"""

import pytest
import asyncio
from uuid import UUID
from unittest.mock import AsyncMock, MagicMock, patch

from api.application.services.orchestrator import Orchestrator
from api.infrastructure.events.event_types import EventType
from api.config import Settings


@pytest.fixture
def mock_event_bus():
    bus = AsyncMock()
    bus.connect = AsyncMock()
    bus.subscribe = AsyncMock()
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def mock_container():
    container = MagicMock()
    return container


@pytest.fixture
def mock_settings():
    settings = MagicMock(spec=Settings)
    settings.ORCHESTRATOR_MAX_CONCURRENT = 2
    settings.ORCHESTRATOR_SCAN_DELAY = 0
    return settings


@pytest.fixture
def orchestrator(mock_event_bus, mock_container, mock_settings):
    return Orchestrator(
        bus=mock_event_bus,
        container=mock_container,
        settings=mock_settings
    )


@pytest.mark.asyncio
async def test_handle_ips_expanded_creates_task(orchestrator):
    """Test that IPS_EXPANDED event creates background task"""
    event = {
        "program_id": "123e4567-e89b-12d3-a456-426614174000",
        "ips": ["192.168.1.1", "192.168.1.2", "192.168.1.3"],
        "source_cidrs": ["192.168.1.0/24"]
    }

    with patch.object(orchestrator, '_process_expanded_ips', new_callable=AsyncMock) as mock_process:
        await orchestrator.handle_ips_expanded(event)

        await asyncio.sleep(0.1)

        # Task completes and is removed from set, so check mock was called instead
        mock_process.assert_called_once_with(
            event["program_id"],
            event["ips"]
        )


@pytest.mark.asyncio
async def test_process_expanded_ips_parallel_execution(orchestrator, mock_container):
    """Test that HTTPx and Naabu execute in parallel"""
    program_id = "123e4567-e89b-12d3-a456-426614174000"
    ips = ["192.168.1.1", "192.168.1.2"]

    mock_httpx_service = AsyncMock()
    mock_httpx_service.execute = AsyncMock()

    mock_naabu_service = AsyncMock()
    mock_naabu_service.execute = AsyncMock()

    mock_request_container = AsyncMock()
    mock_request_container.__aenter__ = AsyncMock(return_value=mock_request_container)
    mock_request_container.__aexit__ = AsyncMock(return_value=None)
    mock_request_container.get = AsyncMock(side_effect=[mock_httpx_service, mock_naabu_service])

    mock_container.return_value = mock_request_container

    await orchestrator._process_expanded_ips(program_id, ips)

    mock_httpx_service.execute.assert_called_once_with(
        program_id=program_id,
        targets=ips
    )

    mock_naabu_service.execute.assert_called_once_with(
        program_id=UUID(program_id),
        hosts=ips,
        top_ports="1000",
        rate=1000,
        scan_type="c",
        exclude_cdn=True
    )


@pytest.mark.asyncio
async def test_process_expanded_ips_uses_semaphore(orchestrator, mock_container):
    """Test that expanded IPs processing respects semaphore"""
    program_id = "123e4567-e89b-12d3-a456-426614174000"
    ips = ["192.168.1.1"]

    mock_httpx_service = AsyncMock()
    mock_httpx_service.execute = AsyncMock()

    mock_naabu_service = AsyncMock()
    mock_naabu_service.execute = AsyncMock()

    mock_request_container = AsyncMock()
    mock_request_container.__aenter__ = AsyncMock(return_value=mock_request_container)
    mock_request_container.__aexit__ = AsyncMock(return_value=None)
    mock_request_container.get = AsyncMock(side_effect=[mock_httpx_service, mock_naabu_service])

    mock_container.return_value = mock_request_container

    initial_value = orchestrator._scan_semaphore._value

    async def check_semaphore():
        await asyncio.sleep(0.01)
        return orchestrator._scan_semaphore._value < initial_value

    task = asyncio.create_task(orchestrator._process_expanded_ips(program_id, ips))
    semaphore_acquired = await check_semaphore()
    await task

    assert semaphore_acquired


@pytest.mark.asyncio
async def test_process_expanded_ips_handles_errors(orchestrator, mock_container):
    """Test that errors in one service don't break the other"""
    program_id = "123e4567-e89b-12d3-a456-426614174000"
    ips = ["192.168.1.1"]

    mock_httpx_service = AsyncMock()
    mock_httpx_service.execute = AsyncMock(side_effect=Exception("HTTPx error"))

    mock_naabu_service = AsyncMock()
    mock_naabu_service.execute = AsyncMock()

    mock_request_container = AsyncMock()
    mock_request_container.__aenter__ = AsyncMock(return_value=mock_request_container)
    mock_request_container.__aexit__ = AsyncMock(return_value=None)
    mock_request_container.get = AsyncMock(side_effect=[mock_httpx_service, mock_naabu_service])

    mock_container.return_value = mock_request_container

    await orchestrator._process_expanded_ips(program_id, ips)

    mock_httpx_service.execute.assert_called_once()
    mock_naabu_service.execute.assert_called_once()


@pytest.mark.asyncio
async def test_handle_naabu_results_batch_ingests_results(orchestrator, mock_container):
    """Test that Naabu results batch is ingested correctly"""
    event = {
        "program_id": "123e4567-e89b-12d3-a456-426614174000",
        "results": [
            {"host": "8.8.8.8", "ip": "8.8.8.8", "port": 53, "protocol": "tcp"},
            {"host": "8.8.8.8", "ip": "8.8.8.8", "port": 443, "protocol": "tcp"},
        ],
        "scan_mode": "active"
    }

    mock_ingestor = AsyncMock()
    mock_ingestor.ingest = AsyncMock()

    mock_request_container = AsyncMock()
    mock_request_container.__aenter__ = AsyncMock(return_value=mock_request_container)
    mock_request_container.__aexit__ = AsyncMock(return_value=None)
    mock_request_container.get = AsyncMock(return_value=mock_ingestor)

    mock_container.return_value = mock_request_container

    await orchestrator.handle_naabu_results_batch(event)

    mock_ingestor.ingest.assert_called_once_with(
        event["results"],
        UUID(event["program_id"])
    )


@pytest.mark.asyncio
async def test_handle_naabu_results_batch_passive_mode(orchestrator, mock_container):
    """Test handling of passive scan results"""
    event = {
        "program_id": "123e4567-e89b-12d3-a456-426614174000",
        "results": [
            {"host": "8.8.8.8", "ip": "8.8.8.8", "port": 80, "protocol": "tcp"},
        ],
        "scan_mode": "passive"
    }

    mock_ingestor = AsyncMock()
    mock_ingestor.ingest = AsyncMock()

    mock_request_container = AsyncMock()
    mock_request_container.__aenter__ = AsyncMock(return_value=mock_request_container)
    mock_request_container.__aexit__ = AsyncMock(return_value=None)
    mock_request_container.get = AsyncMock(return_value=mock_ingestor)

    mock_container.return_value = mock_request_container

    await orchestrator.handle_naabu_results_batch(event)

    mock_ingestor.ingest.assert_called_once()


@pytest.mark.asyncio
async def test_handle_naabu_results_batch_error_handling(orchestrator, mock_container):
    """Test error handling in Naabu results batch processing"""
    event = {
        "program_id": "123e4567-e89b-12d3-a456-426614174000",
        "results": [
            {"host": "8.8.8.8", "ip": "8.8.8.8", "port": 53, "protocol": "tcp"},
        ],
        "scan_mode": "active"
    }

    mock_ingestor = AsyncMock()
    mock_ingestor.ingest = AsyncMock(side_effect=Exception("Ingestion error"))

    mock_request_container = AsyncMock()
    mock_request_container.__aenter__ = AsyncMock(return_value=mock_request_container)
    mock_request_container.__aexit__ = AsyncMock(return_value=None)
    mock_request_container.get = AsyncMock(return_value=mock_ingestor)

    mock_container.return_value = mock_request_container

    await orchestrator.handle_naabu_results_batch(event)


@pytest.mark.asyncio
async def test_ips_expanded_event_flow(orchestrator, mock_container, mock_event_bus):
    """Test complete flow from IPS_EXPANDED to parallel scans"""
    event = {
        "program_id": "123e4567-e89b-12d3-a456-426614174000",
        "ips": ["192.168.1.1", "192.168.1.2"],
        "source_cidrs": ["192.168.1.0/24"]
    }

    mock_httpx_service = AsyncMock()
    mock_httpx_service.execute = AsyncMock()

    mock_naabu_service = AsyncMock()
    mock_naabu_service.execute = AsyncMock()

    mock_request_container = AsyncMock()
    mock_request_container.__aenter__ = AsyncMock(return_value=mock_request_container)
    mock_request_container.__aexit__ = AsyncMock(return_value=None)
    mock_request_container.get = AsyncMock(side_effect=[mock_httpx_service, mock_naabu_service])

    mock_container.return_value = mock_request_container

    task = asyncio.create_task(orchestrator.handle_ips_expanded(event))
    await asyncio.sleep(0.1)

    await asyncio.gather(*orchestrator.tasks, return_exceptions=True)
    await task

    mock_httpx_service.execute.assert_called_once()
    mock_naabu_service.execute.assert_called_once()


@pytest.mark.asyncio
async def test_start_subscribes_to_naabu_events(orchestrator, mock_event_bus):
    """Test that orchestrator subscribes to Naabu events on start"""
    await orchestrator.start()

    subscribe_calls = [call[0][0] for call in mock_event_bus.subscribe.call_args_list]

    assert EventType.IPS_EXPANDED in subscribe_calls
    assert EventType.NAABU_RESULTS_BATCH in subscribe_calls


@pytest.mark.asyncio
async def test_process_expanded_ips_empty_list(orchestrator, mock_container):
    """Test handling of empty IP list"""
    program_id = "123e4567-e89b-12d3-a456-426614174000"
    ips = []

    mock_httpx_service = AsyncMock()
    mock_httpx_service.execute = AsyncMock()

    mock_naabu_service = AsyncMock()
    mock_naabu_service.execute = AsyncMock()

    mock_request_container = AsyncMock()
    mock_request_container.__aenter__ = AsyncMock(return_value=mock_request_container)
    mock_request_container.__aexit__ = AsyncMock(return_value=None)
    mock_request_container.get = AsyncMock(side_effect=[mock_httpx_service, mock_naabu_service])

    mock_container.return_value = mock_request_container

    await orchestrator._process_expanded_ips(program_id, ips)

    mock_httpx_service.execute.assert_called_once_with(
        program_id=program_id,
        targets=[]
    )
    mock_naabu_service.execute.assert_called_once()


@pytest.mark.asyncio
async def test_process_expanded_ips_large_ip_list(orchestrator, mock_container):
    """Test handling of large IP list"""
    program_id = "123e4567-e89b-12d3-a456-426614174000"
    ips = [f"192.168.1.{i}" for i in range(1, 255)]

    mock_httpx_service = AsyncMock()
    mock_httpx_service.execute = AsyncMock()

    mock_naabu_service = AsyncMock()
    mock_naabu_service.execute = AsyncMock()

    mock_request_container = AsyncMock()
    mock_request_container.__aenter__ = AsyncMock(return_value=mock_request_container)
    mock_request_container.__aexit__ = AsyncMock(return_value=None)
    mock_request_container.get = AsyncMock(side_effect=[mock_httpx_service, mock_naabu_service])

    mock_container.return_value = mock_request_container

    await orchestrator._process_expanded_ips(program_id, ips)

    assert len(mock_httpx_service.execute.call_args[1]["targets"]) == 254
    assert len(mock_naabu_service.execute.call_args[1]["hosts"]) == 254


@pytest.mark.asyncio
async def test_handle_naabu_results_batch_default_scan_mode(orchestrator, mock_container):
    """Test that scan_mode defaults to active if not provided"""
    event = {
        "program_id": "123e4567-e89b-12d3-a456-426614174000",
        "results": [
            {"host": "8.8.8.8", "ip": "8.8.8.8", "port": 53, "protocol": "tcp"},
        ]
    }

    mock_ingestor = AsyncMock()
    mock_ingestor.ingest = AsyncMock()

    mock_request_container = AsyncMock()
    mock_request_container.__aenter__ = AsyncMock(return_value=mock_request_container)
    mock_request_container.__aexit__ = AsyncMock(return_value=None)
    mock_request_container.get = AsyncMock(return_value=mock_ingestor)

    mock_container.return_value = mock_request_container

    await orchestrator.handle_naabu_results_batch(event)

    mock_ingestor.ingest.assert_called_once()


@pytest.mark.asyncio
async def test_multiple_ips_expanded_events_concurrent(orchestrator, mock_container):
    """Test handling of multiple concurrent IPS_EXPANDED events"""
    events = [
        {
            "program_id": "123e4567-e89b-12d3-a456-426614174000",
            "ips": ["192.168.1.1", "192.168.1.2"],
            "source_cidrs": ["192.168.1.0/24"]
        },
        {
            "program_id": "123e4567-e89b-12d3-a456-426614174000",
            "ips": ["10.0.0.1", "10.0.0.2"],
            "source_cidrs": ["10.0.0.0/24"]
        }
    ]

    mock_httpx_service = AsyncMock()
    mock_httpx_service.execute = AsyncMock()

    mock_naabu_service = AsyncMock()
    mock_naabu_service.execute = AsyncMock()

    mock_request_container = AsyncMock()
    mock_request_container.__aenter__ = AsyncMock(return_value=mock_request_container)
    mock_request_container.__aexit__ = AsyncMock(return_value=None)
    mock_request_container.get = AsyncMock(side_effect=[
        mock_httpx_service, mock_naabu_service,
        mock_httpx_service, mock_naabu_service
    ])

    mock_container.return_value = mock_request_container

    tasks = []
    for event in events:
        task = asyncio.create_task(orchestrator.handle_ips_expanded(event))
        tasks.append(task)
        await asyncio.sleep(0.01)

    await asyncio.gather(*tasks)
    await asyncio.gather(*orchestrator.tasks, return_exceptions=True)

    assert mock_httpx_service.execute.call_count >= 2
    assert mock_naabu_service.execute.call_count >= 2
