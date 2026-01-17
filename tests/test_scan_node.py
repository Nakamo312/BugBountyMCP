"""Tests for ScanNode (created by NodeFactory)"""
import pytest
from unittest.mock import AsyncMock
from uuid import uuid4

from api.application.pipeline.factory import NodeFactory
from api.infrastructure.events.event_types import EventType
from api.infrastructure.runners.httpx_cli import HTTPXCliRunner
from api.application.services.batch_processor import HTTPXBatchProcessor
from api.infrastructure.ingestors.httpx_ingestor import HTTPXResultIngestor
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
    """Mock HTTPX CLI runner"""
    class MockRunMethod:
        def __init__(self):
            self.call_count = 0

        async def __call__(self, targets):
            self.call_count += 1
            yield ProcessEvent(type="result", payload={"host": "example.com", "status_code": 200})
            yield ProcessEvent(type="result", payload={"host": "test.com", "status_code": 200})
            yield ProcessEvent(type="result", payload={"host": "demo.com", "status_code": 200})

    runner = AsyncMock(spec=HTTPXCliRunner)
    runner.run = MockRunMethod()
    return runner


@pytest.fixture
def mock_processor():
    """Mock batch processor"""
    processor = AsyncMock(spec=HTTPXBatchProcessor)

    async def batch_gen(stream):
        batch = []
        async for event in stream:
            batch.append(event.payload)
            if len(batch) >= 2:
                yield batch
                batch = []
        if batch:
            yield batch

    processor.batch_stream = batch_gen
    return processor


@pytest.fixture
def mock_ingestor():
    """Mock HTTPX ingestor"""
    ingestor = AsyncMock(spec=HTTPXResultIngestor)
    ingestor.ingest = AsyncMock(return_value=IngestResult(new_hosts=["host1.com", "host2.com"], js_files=["app.js"]))
    return ingestor


@pytest.mark.asyncio
async def test_scan_node_processes_event(mock_context, mock_runner, mock_processor, mock_ingestor):
    """Test ScanNode processes event and calls runner/processor/ingestor"""
    mock_context.get_service = AsyncMock(side_effect=lambda cls: {
        HTTPXCliRunner: mock_runner,
        HTTPXBatchProcessor: mock_processor,
        HTTPXResultIngestor: mock_ingestor
    }[cls])

    node = NodeFactory.create_scan_node(
        node_id="httpx",
        event_in={EventType.HTTPX_SCAN_REQUESTED},
        event_out={
            EventType.HOST_DISCOVERED: "new_hosts",
            EventType.JS_FILES_DISCOVERED: "js_files"
        },
        runner_type=HTTPXCliRunner,
        processor_type=HTTPXBatchProcessor,
        ingestor_type=HTTPXResultIngestor,
        max_parallelism=1
    )

    event = {
        "event": "httpx_scan_requested",
        "program_id": str(uuid4()),
        "targets": ["example.com"]
    }

    await node.execute(event, mock_context)

    # Check that runner was called
    mock_context.get_service.assert_any_call(HTTPXCliRunner)

    # Check that ingestor was called
    mock_ingestor.ingest.assert_called()


@pytest.mark.asyncio
async def test_scan_node_returns_empty_result_on_no_data(mock_context, mock_ingestor):
    """Test ScanNode returns empty IngestResult when no data"""
    runner = AsyncMock()

    async def empty_gen(targets):
        if False:
            yield

    runner.run = empty_gen

    processor = AsyncMock()

    async def empty_batch_gen(stream):
        async for _ in stream:
            pass
        return
        yield

    processor.batch_stream = empty_batch_gen

    mock_context.get_service = AsyncMock(side_effect=lambda cls: {
        HTTPXCliRunner: runner,
        HTTPXBatchProcessor: processor,
        HTTPXResultIngestor: mock_ingestor
    }[cls])

    node = NodeFactory.create_scan_node(
        node_id="httpx",
        event_in={EventType.HTTPX_SCAN_REQUESTED},
        event_out={EventType.HOST_DISCOVERED: "new_hosts"},
        runner_type=HTTPXCliRunner,
        processor_type=HTTPXBatchProcessor,
        ingestor_type=HTTPXResultIngestor,
        max_parallelism=1
    )

    event = {
        "event": "httpx_scan_requested",
        "program_id": str(uuid4()),
        "targets": ["example.com"]
    }

    result = await node.execute(event, mock_context)

    # Ingestor should not be called if no batches
    mock_ingestor.ingest.assert_not_called()


@pytest.mark.asyncio
async def test_scan_node_handles_multiple_batches(mock_context, mock_ingestor):
    """Test ScanNode handles multiple batches correctly"""
    runner = AsyncMock()

    async def multi_gen(targets):
        for i in range(10):
            yield ProcessEvent(type="result", payload={"host": f"host{i}.com", "status_code": 200})

    runner.run = multi_gen

    processor = AsyncMock()

    async def batch_gen(stream):
        batch = []
        async for event in stream:
            batch.append(event.payload)
            if len(batch) >= 3:
                yield batch
                batch = []
        if batch:
            yield batch

    processor.batch_stream = batch_gen

    mock_ingestor.ingest = AsyncMock(return_value=IngestResult(new_hosts=["host.com"]))

    mock_context.get_service = AsyncMock(side_effect=lambda cls: {
        HTTPXCliRunner: runner,
        HTTPXBatchProcessor: processor,
        HTTPXResultIngestor: mock_ingestor
    }[cls])

    node = NodeFactory.create_scan_node(
        node_id="httpx",
        event_in={EventType.HTTPX_SCAN_REQUESTED},
        event_out={EventType.HOST_DISCOVERED: "new_hosts"},
        runner_type=HTTPXCliRunner,
        processor_type=HTTPXBatchProcessor,
        ingestor_type=HTTPXResultIngestor,
        max_parallelism=1
    )

    event = {
        "event": "httpx_scan_requested",
        "program_id": str(uuid4()),
        "targets": [f"host{i}.com" for i in range(10)]
    }

    await node.execute(event, mock_context)

    # Should be called 4 times (10 items / 3 batch size = 3 full + 1 partial)
    assert mock_ingestor.ingest.call_count == 4
