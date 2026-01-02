import pytest
from unittest.mock import AsyncMock
from uuid import uuid4

from api.application.services.gau import GAUScanService


@pytest.fixture
def mock_gau_runner():
    """Mock GAUCliRunner"""
    runner = AsyncMock()
    return runner


@pytest.fixture
def mock_gau_processor():
    """Mock GAUBatchProcessor"""
    processor = AsyncMock()
    return processor


@pytest.fixture
def mock_event_bus():
    """Mock EventBus"""
    bus = AsyncMock()
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def gau_service(mock_gau_runner, mock_gau_processor, mock_event_bus):
    """GAUScanService with mocked dependencies"""
    return GAUScanService(
        runner=mock_gau_runner,
        processor=mock_gau_processor,
        bus=mock_event_bus
    )


@pytest.mark.asyncio
async def test_run_scan_publishes_url_batches(gau_service, mock_gau_runner, mock_gau_processor, mock_event_bus):
    """Test _run_scan publishes URL batches"""
    program_id = uuid4()
    domain = "example.com"

    async def mock_batch_stream(runner_gen):
        yield ["https://example.com/api/users", "https://example.com/page1"]
        yield ["https://example.com/page2", "https://example.com/style.css"]

    mock_gau_processor.batch_stream = mock_batch_stream

    await gau_service._run_scan(program_id, domain, True)

    assert mock_event_bus.publish.call_count == 2

    gau_publish_calls = [
        call for call in mock_event_bus.publish.call_args_list
        if call[0][0].value == "gau_discovered"
    ]

    assert len(gau_publish_calls) == 2


@pytest.mark.asyncio
async def test_publish_batch_uses_correct_event_type(gau_service, mock_event_bus):
    """Test _publish_batch uses GAU_DISCOVERED event type"""
    program_id = uuid4()
    urls = ["https://example.com/page1", "https://example.com/page2"]

    await gau_service._publish_batch(program_id, urls)

    mock_event_bus.publish.assert_called_once()
    call_args = mock_event_bus.publish.call_args[0]
    assert call_args[0].value == "gau_discovered"
    assert call_args[1]["program_id"] == str(program_id)
    assert call_args[1]["urls"] == urls
