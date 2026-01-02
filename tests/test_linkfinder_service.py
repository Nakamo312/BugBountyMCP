import pytest
from unittest.mock import AsyncMock
from uuid import uuid4

from api.application.services.linkfinder import LinkFinderScanService
from api.infrastructure.schemas.models.process_event import ProcessEvent


@pytest.fixture
def mock_linkfinder_runner():
    """Mock LinkFinderCliRunner"""
    runner = AsyncMock()
    return runner


@pytest.fixture
def mock_event_bus():
    """Mock EventBus"""
    bus = AsyncMock()
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def linkfinder_service(mock_linkfinder_runner, mock_event_bus):
    """LinkFinderScanService with mocked dependencies"""
    return LinkFinderScanService(
        runner=mock_linkfinder_runner,
        bus=mock_event_bus
    )


@pytest.mark.asyncio
async def test_execute_returns_started_status(linkfinder_service):
    """Test execute returns started status immediately"""
    program_id = uuid4()
    targets = ["https://example.com/app.js", "https://example.com/bundle.js"]

    result = await linkfinder_service.execute(program_id, targets)

    assert result.status == "started"
    assert result.scanner == "linkfinder"
    assert result.targets_count == 2
    assert "2 JS files" in result.message


@pytest.mark.asyncio
async def test_execute_single_target(linkfinder_service):
    """Test execute with single target"""
    program_id = uuid4()
    targets = ["https://example.com/app.js"]

    result = await linkfinder_service.execute(program_id, targets)

    assert result.targets_count == 1
    assert "1 JS files" in result.message


@pytest.mark.asyncio
async def test_run_scan_publishes_results(linkfinder_service, mock_linkfinder_runner, mock_event_bus):
    """Test _run_scan publishes discovered URLs to GAU_DISCOVERED event"""
    program_id = uuid4()
    targets = ["https://example.com/app.js"]

    result_event = ProcessEvent(
        type="result",
        payload={
            "source_js": "https://example.com/app.js",
            "urls": [
                "https://example.com/api/users",
                "https://example.com/api/products"
            ],
            "host": "example.com"
        }
    )

    async def mock_run_generator(targets):
        yield result_event

    mock_linkfinder_runner.run = mock_run_generator

    await linkfinder_service._run_scan(program_id, targets)

    mock_event_bus.publish.assert_called_once()
    call_args = mock_event_bus.publish.call_args[0]
    assert call_args[0].value == "gau_discovered"
    assert call_args[1]["program_id"] == str(program_id)
    assert call_args[1]["urls"] == [
        "https://example.com/api/users",
        "https://example.com/api/products"
    ]


@pytest.mark.asyncio
async def test_run_scan_handles_multiple_results(linkfinder_service, mock_linkfinder_runner, mock_event_bus):
    """Test _run_scan aggregates URLs from multiple result events"""
    program_id = uuid4()
    targets = ["https://example.com/app.js", "https://example.com/vendor.js"]

    result1 = ProcessEvent(
        type="result",
        payload={
            "source_js": "https://example.com/app.js",
            "urls": ["https://example.com/api/users"],
            "host": "example.com"
        }
    )

    result2 = ProcessEvent(
        type="result",
        payload={
            "source_js": "https://example.com/vendor.js",
            "urls": ["https://example.com/api/products", "https://example.com/api/cart"],
            "host": "example.com"
        }
    )

    async def mock_run_generator(targets):
        yield result1
        yield result2

    mock_linkfinder_runner.run = mock_run_generator

    await linkfinder_service._run_scan(program_id, targets)

    mock_event_bus.publish.assert_called_once()
    call_args = mock_event_bus.publish.call_args[0]
    assert call_args[0].value == "gau_discovered"
    assert call_args[1]["urls"] == [
        "https://example.com/api/users",
        "https://example.com/api/products",
        "https://example.com/api/cart"
    ]


@pytest.mark.asyncio
async def test_run_scan_skips_non_result_events(linkfinder_service, mock_linkfinder_runner, mock_event_bus):
    """Test _run_scan skips non-result events"""
    program_id = uuid4()
    targets = ["https://example.com/app.js"]

    stdout_event = ProcessEvent(type="stdout", payload="Processing...")
    result_event = ProcessEvent(
        type="result",
        payload={
            "source_js": "https://example.com/app.js",
            "urls": ["https://example.com/api/users"],
            "host": "example.com"
        }
    )

    async def mock_run_generator(targets):
        yield stdout_event
        yield result_event

    mock_linkfinder_runner.run = mock_run_generator

    await linkfinder_service._run_scan(program_id, targets)

    assert mock_event_bus.publish.call_count == 1


@pytest.mark.asyncio
async def test_run_scan_handles_empty_results(linkfinder_service, mock_linkfinder_runner, mock_event_bus):
    """Test _run_scan handles empty results gracefully"""
    program_id = uuid4()
    targets = ["https://example.com/app.js"]

    async def mock_run_generator(targets):
        return
        yield

    mock_linkfinder_runner.run = mock_run_generator

    await linkfinder_service._run_scan(program_id, targets)

    mock_event_bus.publish.assert_not_called()


@pytest.mark.asyncio
async def test_run_scan_handles_exception(linkfinder_service, mock_linkfinder_runner, mock_event_bus):
    """Test _run_scan handles exceptions gracefully"""
    program_id = uuid4()
    targets = ["https://example.com/app.js"]

    async def mock_run_generator(targets):
        raise Exception("LinkFinder execution failed")
        yield

    mock_linkfinder_runner.run = mock_run_generator

    # Should not raise exception
    await linkfinder_service._run_scan(program_id, targets)

    mock_event_bus.publish.assert_not_called()


@pytest.mark.asyncio
async def test_publish_urls_for_httpx_includes_program_id(linkfinder_service, mock_event_bus):
    """Test _publish_urls_for_httpx includes program_id in event payload"""
    program_id = uuid4()
    urls = ["https://example.com/api/users", "https://example.com/api/products"]

    await linkfinder_service._publish_urls_for_httpx(program_id, urls)

    call_args = mock_event_bus.publish.call_args[0]
    assert call_args[1]["program_id"] == str(program_id)
    assert call_args[1]["urls"] == urls


@pytest.mark.asyncio
async def test_publish_urls_for_httpx_uses_correct_event_type(linkfinder_service, mock_event_bus):
    """Test _publish_urls_for_httpx uses GAU_DISCOVERED event type"""
    program_id = uuid4()
    urls = ["https://example.com/api/users"]

    await linkfinder_service._publish_urls_for_httpx(program_id, urls)

    call_args = mock_event_bus.publish.call_args[0]
    assert call_args[0].value == "gau_discovered"
