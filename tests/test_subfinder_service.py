import pytest
from unittest.mock import AsyncMock, call
from uuid import uuid4
import asyncio

from api.application.services.subfinder import SubfinderScanService
from api.infrastructure.events.event_types import EventType


@pytest.fixture
def mock_runner():
    return AsyncMock()


@pytest.fixture
def mock_processor():
    processor = AsyncMock()
    processor.batch_stream = AsyncMock()
    return processor


@pytest.fixture
def mock_event_bus():
    bus = AsyncMock()
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def subfinder_service(mock_runner, mock_processor, mock_event_bus):
    return SubfinderScanService(
        runner=mock_runner,
        processor=mock_processor,
        bus=mock_event_bus
    )


@pytest.mark.asyncio
async def test_execute_returns_immediately(subfinder_service, sample_program):
    """Test execute returns immediately without waiting for scan"""
    result = await subfinder_service.execute(sample_program.id, "example.com")

    assert result.status == "started"
    assert result.scanner == "subfinder"
    assert result.domain == "example.com"


@pytest.mark.asyncio
async def test_publish_batch_publishes_event(subfinder_service, mock_event_bus, sample_program):
    """Test _publish_batch publishes SUBDOMAIN_DISCOVERED event"""
    subdomains = ["api.example.com", "www.example.com", "mail.example.com"]

    await subfinder_service._publish_batch(sample_program.id, subdomains)

    mock_event_bus.publish.assert_called_once()
    call_args = mock_event_bus.publish.call_args
    assert call_args[0][0] == EventType.SUBDOMAIN_DISCOVERED
    assert call_args[0][1]["program_id"] == str(sample_program.id)
    assert call_args[0][1]["subdomains"] == subdomains


@pytest.mark.asyncio
async def test_run_scan_processes_batches(subfinder_service, mock_processor, mock_event_bus, sample_program):
    """Test _run_scan processes and publishes batches"""

    async def mock_batch_stream(stream):
        yield ["sub1.example.com", "sub2.example.com"]
        yield ["sub3.example.com"]

    mock_processor.batch_stream = mock_batch_stream

    await subfinder_service._run_scan(sample_program.id, "example.com")

    assert mock_event_bus.publish.call_count == 2


@pytest.mark.asyncio
async def test_run_scan_handles_errors(subfinder_service, mock_processor, mock_event_bus, sample_program):
    """Test _run_scan handles errors gracefully"""

    async def failing_batch_stream(stream):
        yield ["sub1.example.com"]
        raise Exception("Scan failed")

    mock_processor.batch_stream = failing_batch_stream

    # Should not raise exception
    await subfinder_service._run_scan(sample_program.id, "example.com")

    # Should have published one batch before error
    assert mock_event_bus.publish.call_count == 1
