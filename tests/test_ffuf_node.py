"""Tests for FFUFNode (custom node with parallelism)"""
import pytest
from unittest.mock import AsyncMock
from uuid import uuid4

from api.application.pipeline.nodes.ffuf_node import FFUFNode
from api.infrastructure.events.event_types import EventType
from api.infrastructure.runners.ffuf_cli import FFUFCliRunner
from api.infrastructure.ingestors.ffuf_ingestor import FFUFResultIngestor
from api.infrastructure.ingestors.ingest_result import IngestResult
from api.infrastructure.schemas.models.process_event import ProcessEvent


@pytest.fixture
def mock_context():
    """Mock PipelineContext"""
    ctx = AsyncMock()
    ctx.get_service = AsyncMock()
    return ctx


@pytest.fixture
def mock_runner():
    """Mock FFUF CLI runner"""
    class MockRunMethod:
        def __init__(self):
            self.call_count = 0

        async def __call__(self, target_url):
            self.call_count += 1
            yield ProcessEvent(type="result", payload={"url": f"{target_url}/admin", "status": 200})
            yield ProcessEvent(type="result", payload={"url": f"{target_url}/api", "status": 200})

    runner = AsyncMock(spec=FFUFCliRunner)
    runner.run = MockRunMethod()
    return runner


@pytest.fixture
def mock_ingestor():
    """Mock FFUF ingestor"""
    ingestor = AsyncMock(spec=FFUFResultIngestor)
    ingestor.ingest = AsyncMock(return_value=IngestResult())
    return ingestor


@pytest.mark.asyncio
async def test_ffuf_node_processes_single_target(mock_context, mock_runner, mock_ingestor):
    """Test FFUFNode processes single target"""
    mock_context.get_service = AsyncMock(side_effect=lambda cls: {
        FFUFCliRunner: mock_runner,
        FFUFResultIngestor: mock_ingestor
    }[cls])

    node = FFUFNode(
        node_id="ffuf",
        event_in={EventType.FFUF_SCAN_REQUESTED},
        max_parallelism=1,
        max_concurrent_scans=5
    )

    event = {
        "event": "ffuf_scan_requested",
        "program_id": str(uuid4()),
        "targets": ["https://example.com"]
    }

    await node.execute(event, mock_context)

    # Runner should be called once
    assert mock_runner.run.call_count == 1

    # Ingestor should be called with results
    mock_ingestor.ingest.assert_called_once()
    call_args = mock_ingestor.ingest.call_args
    assert len(call_args[0][1]) == 2  # 2 results


@pytest.mark.asyncio
async def test_ffuf_node_processes_multiple_targets_in_parallel(mock_context, mock_runner, mock_ingestor):
    """Test FFUFNode processes multiple targets in parallel"""
    mock_context.get_service = AsyncMock(side_effect=lambda cls: {
        FFUFCliRunner: mock_runner,
        FFUFResultIngestor: mock_ingestor
    }[cls])

    node = FFUFNode(
        node_id="ffuf",
        event_in={EventType.FFUF_SCAN_REQUESTED},
        max_parallelism=3,
        max_concurrent_scans=5
    )

    event = {
        "event": "ffuf_scan_requested",
        "program_id": str(uuid4()),
        "targets": [
            "https://example.com",
            "https://test.com",
            "https://demo.com"
        ]
    }

    await node.execute(event, mock_context)

    # Runner should be called 3 times (once per target)
    assert mock_runner.run.call_count == 3

    # Ingestor should be called 3 times (once per target with results)
    assert mock_ingestor.ingest.call_count == 3


@pytest.mark.asyncio
async def test_ffuf_node_skips_non_string_targets(mock_context, mock_runner, mock_ingestor):
    """Test FFUFNode skips invalid targets"""
    mock_context.get_service = AsyncMock(side_effect=lambda cls: {
        FFUFCliRunner: mock_runner,
        FFUFResultIngestor: mock_ingestor
    }[cls])

    node = FFUFNode(
        node_id="ffuf",
        event_in={EventType.FFUF_SCAN_REQUESTED},
        max_parallelism=1,
        max_concurrent_scans=5
    )

    event = {
        "event": "ffuf_scan_requested",
        "program_id": str(uuid4()),
        "targets": [
            "https://example.com",
            None,  # Invalid
            123,   # Invalid
            "https://test.com"
        ]
    }

    await node.execute(event, mock_context)

    # Only 2 valid targets should be processed
    assert mock_runner.run.call_count == 2


@pytest.mark.asyncio
async def test_ffuf_node_respects_semaphore_limit(mock_context, mock_ingestor):
    """Test FFUFNode respects max_concurrent_scans semaphore"""
    concurrent_count = 0
    max_concurrent = 0

    class MockRunMethod:
        def __init__(self):
            self.call_count = 0

        async def __call__(self, target_url):
            nonlocal concurrent_count, max_concurrent
            self.call_count += 1
            concurrent_count += 1
            if concurrent_count > max_concurrent:
                max_concurrent = concurrent_count

            # Simulate some work
            import asyncio
            await asyncio.sleep(0.01)

            yield ProcessEvent(type="result", payload={"url": f"{target_url}/test", "status": 200})

            concurrent_count -= 1

    runner = AsyncMock()
    runner.run = MockRunMethod()

    mock_context.get_service = AsyncMock(side_effect=lambda cls: {
        FFUFCliRunner: runner,
        FFUFResultIngestor: mock_ingestor
    }[cls])

    node = FFUFNode(
        node_id="ffuf",
        event_in={EventType.FFUF_SCAN_REQUESTED},
        max_parallelism=10,
        max_concurrent_scans=3  # Limit to 3 concurrent
    )

    event = {
        "event": "ffuf_scan_requested",
        "program_id": str(uuid4()),
        "targets": [f"https://target{i}.com" for i in range(10)]
    }

    await node.execute(event, mock_context)

    # Max concurrent should not exceed semaphore limit
    assert max_concurrent <= 3


@pytest.mark.asyncio
async def test_ffuf_node_handles_empty_results(mock_context, mock_ingestor):
    """Test FFUFNode handles targets with no results"""
    class MockRunMethod:
        def __init__(self):
            self.call_count = 0

        async def __call__(self, target_url):
            self.call_count += 1
            if False:
                yield

    runner = AsyncMock()
    runner.run = MockRunMethod()

    mock_context.get_service = AsyncMock(side_effect=lambda cls: {
        FFUFCliRunner: runner,
        FFUFResultIngestor: mock_ingestor
    }[cls])

    node = FFUFNode(
        node_id="ffuf",
        event_in={EventType.FFUF_SCAN_REQUESTED},
        max_parallelism=1,
        max_concurrent_scans=5
    )

    event = {
        "event": "ffuf_scan_requested",
        "program_id": str(uuid4()),
        "targets": ["https://example.com"]
    }

    await node.execute(event, mock_context)

    # Runner called but no results
    assert runner.run.call_count == 1

    # Ingestor should NOT be called (no results)
    mock_ingestor.ingest.assert_not_called()
