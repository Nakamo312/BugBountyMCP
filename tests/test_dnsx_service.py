import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from api.application.services.dnsx import DNSxScanService
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
def dnsx_service(mock_runner, mock_processor, mock_event_bus):
    return DNSxScanService(
        runner=mock_runner,
        processor=mock_processor,
        bus=mock_event_bus
    )


@pytest.mark.asyncio
async def test_execute_basic_mode(dnsx_service, sample_program):
    """Test DNSx Basic mode execution"""
    result = await dnsx_service.execute(
        program_id=sample_program.id,
        targets=["example.com", "test.com"],
        mode="basic"
    )

    assert result.status == "completed"
    assert result.scanner == "dnsx"
    assert result.targets_count == 2
    assert result.mode == "basic"


@pytest.mark.asyncio
async def test_execute_deep_mode(dnsx_service, sample_program):
    """Test DNSx Deep mode execution"""
    result = await dnsx_service.execute(
        program_id=sample_program.id,
        targets=["example.com"],
        mode="deep"
    )

    assert result.status == "completed"
    assert result.scanner == "dnsx"
    assert result.targets_count == 1
    assert result.mode == "deep"


@pytest.mark.asyncio
async def test_run_scan_calls_runner_basic(dnsx_service, mock_runner, mock_processor, sample_program):
    """Test _run_scan calls runner with basic mode"""
    mock_processor.batch_stream.return_value = AsyncMock()
    mock_processor.batch_stream.return_value.__aiter__.return_value = []

    await dnsx_service._run_scan(sample_program.id, ["example.com"], "basic")

    mock_runner.run_basic.assert_called_once_with(["example.com"])


@pytest.mark.asyncio
async def test_run_scan_calls_runner_deep(dnsx_service, mock_runner, mock_processor, sample_program):
    """Test _run_scan calls runner with deep mode"""
    mock_processor.batch_stream.return_value = AsyncMock()
    mock_processor.batch_stream.return_value.__aiter__.return_value = []

    await dnsx_service._run_scan(sample_program.id, ["example.com"], "deep")

    mock_runner.run_deep.assert_called_once_with(["example.com"])


@pytest.mark.asyncio
async def test_publish_batch_basic_publishes_event(dnsx_service, mock_event_bus, sample_program):
    """Test _publish_batch publishes DNSX_BASIC_RESULTS_BATCH event"""
    results = [
        {"host": "example.com", "a": ["1.2.3.4"], "wildcard": False},
        {"host": "test.com", "a": ["5.6.7.8"], "wildcard": False}
    ]

    await dnsx_service._publish_batch(sample_program.id, results, "basic")

    mock_event_bus.publish.assert_called_once()
    call_args = mock_event_bus.publish.call_args
    assert call_args[0][0] == EventType.DNSX_BASIC_RESULTS_BATCH
    assert call_args[0][1]["program_id"] == str(sample_program.id)
    assert call_args[0][1]["results"] == results


@pytest.mark.asyncio
async def test_publish_batch_deep_publishes_event(dnsx_service, mock_event_bus, sample_program):
    """Test _publish_batch publishes DNSX_DEEP_RESULTS_BATCH event"""
    results = [
        {
            "host": "example.com",
            "a": ["1.2.3.4"],
            "mx": ["mail.example.com"],
            "txt": ["v=spf1 include:_spf.google.com ~all"],
            "wildcard": False
        }
    ]

    await dnsx_service._publish_batch(sample_program.id, results, "deep")

    mock_event_bus.publish.assert_called_once()
    call_args = mock_event_bus.publish.call_args
    assert call_args[0][0] == EventType.DNSX_DEEP_RESULTS_BATCH
    assert call_args[0][1]["program_id"] == str(sample_program.id)
    assert call_args[0][1]["results"] == results


@pytest.mark.asyncio
async def test_run_scan_processes_batches(dnsx_service, mock_runner, mock_processor, mock_event_bus, sample_program):
    """Test _run_scan processes multiple batches"""
    batch1 = [{"host": "example.com", "a": ["1.2.3.4"], "wildcard": False}]
    batch2 = [{"host": "test.com", "a": ["5.6.7.8"], "wildcard": False}]

    async def batch_generator(*args, **kwargs):
        yield batch1
        yield batch2

    mock_processor.batch_stream = batch_generator

    await dnsx_service._run_scan(sample_program.id, ["example.com", "test.com"], "basic")

    assert mock_event_bus.publish.call_count == 2
