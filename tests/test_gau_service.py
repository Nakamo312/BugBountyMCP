import pytest
from unittest.mock import AsyncMock, MagicMock
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
async def test_is_js_file_detects_js_extension(gau_service):
    """Test _is_js_file detects .js extension"""
    assert gau_service._is_js_file("https://example.com/app.js") is True
    assert gau_service._is_js_file("https://example.com/bundle.min.js") is True
    assert gau_service._is_js_file("https://example.com/APP.JS") is True


@pytest.mark.asyncio
async def test_is_js_file_detects_js_with_query_params(gau_service):
    """Test _is_js_file detects .js with query parameters"""
    assert gau_service._is_js_file("https://example.com/app.js?v=123") is True
    assert gau_service._is_js_file("https://example.com/bundle.js?t=456&v=1") is True


@pytest.mark.asyncio
async def test_is_js_file_rejects_non_js_files(gau_service):
    """Test _is_js_file rejects non-JS files"""
    assert gau_service._is_js_file("https://example.com/style.css") is False
    assert gau_service._is_js_file("https://example.com/image.png") is False
    assert gau_service._is_js_file("https://example.com/api/users") is False
    assert gau_service._is_js_file("https://example.com/json") is False


@pytest.mark.asyncio
async def test_run_scan_publishes_js_files(gau_service, mock_gau_runner, mock_gau_processor, mock_event_bus):
    """Test _run_scan publishes discovered JS files"""
    program_id = uuid4()
    domain = "example.com"

    async def mock_batch_stream(runner_gen):
        yield ["https://example.com/app.js", "https://example.com/api/users"]
        yield ["https://example.com/bundle.js", "https://example.com/style.css"]

    mock_gau_processor.batch_stream = mock_batch_stream

    await gau_service._run_scan(program_id, domain, True)

    assert mock_event_bus.publish.call_count == 3

    js_publish_calls = [
        call for call in mock_event_bus.publish.call_args_list
        if call[0][0].value == "js_files_discovered"
    ]

    assert len(js_publish_calls) == 1
    js_files = js_publish_calls[0][0][1]["js_files"]
    assert len(js_files) == 2
    assert "https://example.com/app.js" in js_files
    assert "https://example.com/bundle.js" in js_files


@pytest.mark.asyncio
async def test_run_scan_does_not_publish_if_no_js_files(gau_service, mock_gau_runner, mock_gau_processor, mock_event_bus):
    """Test _run_scan does not publish JS files if none found"""
    program_id = uuid4()
    domain = "example.com"

    async def mock_batch_stream(runner_gen):
        yield ["https://example.com/api/users", "https://example.com/style.css"]
        yield ["https://example.com/image.png"]

    mock_gau_processor.batch_stream = mock_batch_stream

    await gau_service._run_scan(program_id, domain, True)

    js_publish_calls = [
        call for call in mock_event_bus.publish.call_args_list
        if call[0][0].value == "js_files_discovered"
    ]

    assert len(js_publish_calls) == 0


@pytest.mark.asyncio
async def test_publish_js_files_uses_correct_event_type(gau_service, mock_event_bus):
    """Test _publish_js_files uses JS_FILES_DISCOVERED event type"""
    program_id = uuid4()
    js_files = ["https://example.com/app.js", "https://example.com/bundle.js"]

    await gau_service._publish_js_files(program_id, js_files)

    mock_event_bus.publish.assert_called_once()
    call_args = mock_event_bus.publish.call_args[0]
    assert call_args[0].value == "js_files_discovered"
    assert call_args[1]["program_id"] == str(program_id)
    assert call_args[1]["js_files"] == js_files
