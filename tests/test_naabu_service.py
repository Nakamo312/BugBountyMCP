"""Tests for Naabu Service"""

import pytest
from uuid import UUID
from unittest.mock import AsyncMock, MagicMock, patch

from api.application.services.naabu import NaabuScanService
from api.application.dto.scan_dto import NaabuScanOutputDTO
from api.infrastructure.events.event_types import EventType
from api.infrastructure.commands.command_executor import ProcessEvent


@pytest.fixture
def mock_runner():
    runner = AsyncMock()
    return runner


@pytest.fixture
def mock_processor():
    processor = AsyncMock()
    return processor


@pytest.fixture
def mock_event_bus():
    bus = AsyncMock()
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def naabu_service(mock_runner, mock_processor, mock_event_bus):
    return NaabuScanService(
        runner=mock_runner,
        processor=mock_processor,
        bus=mock_event_bus
    )


@pytest.fixture
def sample_naabu_results():
    return [
        {"host": "8.8.8.8", "ip": "8.8.8.8", "port": 53, "protocol": "tcp"},
        {"host": "8.8.8.8", "ip": "8.8.8.8", "port": 443, "protocol": "tcp"},
        {"host": "1.1.1.1", "ip": "1.1.1.1", "port": 80, "protocol": "tcp"},
        {"host": "1.1.1.1", "ip": "1.1.1.1", "port": 443, "protocol": "tcp"},
    ]


@pytest.mark.asyncio
async def test_execute_active_scan(naabu_service, mock_runner, mock_processor, mock_event_bus, sample_naabu_results):
    """Test active port scan execution"""
    program_id = UUID("123e4567-e89b-12d3-a456-426614174000")
    hosts = ["8.8.8.8", "1.1.1.1"]

    async def mock_scan(**kwargs):
        for result in sample_naabu_results:
            yield ProcessEvent(type="result", payload=result)

    mock_runner.scan = mock_scan

    async def mock_process(events, **kwargs):
        batch = [event.payload for event in events]
        yield batch

    mock_processor.process = mock_process

    result = await naabu_service.execute(
        program_id=program_id,
        hosts=hosts,
        ports=None,
        top_ports="1000",
        rate=1000,
        scan_type="c",
        exclude_cdn=True
    )

    assert isinstance(result, NaabuScanOutputDTO)
    assert result.status == "completed"
    assert result.scanner == "naabu"
    assert result.targets_count == 2
    assert result.scan_mode == "active"

    assert mock_event_bus.publish.called


@pytest.mark.asyncio
async def test_execute_with_custom_ports(naabu_service, mock_runner, mock_processor, mock_event_bus):
    """Test active scan with custom port specification"""
    program_id = UUID("123e4567-e89b-12d3-a456-426614174000")
    hosts = ["example.com"]
    custom_ports = "80,443,8080-8090"

    async def mock_scan(**kwargs):
        yield ProcessEvent(type="result", payload={"host": "example.com", "ip": "93.184.216.34", "port": 80, "protocol": "tcp"})

    mock_runner.scan = mock_scan

    async def mock_process(events, **kwargs):
        yield [{"host": "example.com", "ip": "93.184.216.34", "port": 80, "protocol": "tcp"}]

    mock_processor.process = mock_process

    result = await naabu_service.execute(
        program_id=program_id,
        hosts=hosts,
        ports=custom_ports,
        top_ports="1000",
        rate=500,
        scan_type="s",
        exclude_cdn=False
    )

    assert result.status == "completed"


@pytest.mark.asyncio
async def test_execute_passive_scan(naabu_service, mock_runner, mock_processor, mock_event_bus):
    """Test passive port enumeration"""
    program_id = UUID("123e4567-e89b-12d3-a456-426614174000")
    hosts = ["8.8.8.8", "1.1.1.1"]

    async def mock_passive(**kwargs):
        yield ProcessEvent(type="result", payload={"host": "8.8.8.8", "ip": "8.8.8.8", "port": 53, "protocol": "tcp"})
        yield ProcessEvent(type="result", payload={"host": "8.8.8.8", "ip": "8.8.8.8", "port": 443, "protocol": "tcp"})

    mock_runner.passive_scan = mock_passive

    async def mock_process(events, **kwargs):
        batch = [
            {"host": "8.8.8.8", "ip": "8.8.8.8", "port": 53, "protocol": "tcp"},
            {"host": "8.8.8.8", "ip": "8.8.8.8", "port": 443, "protocol": "tcp"}
        ]
        yield batch

    mock_processor.process = mock_process

    result = await naabu_service.execute_passive(
        program_id=program_id,
        hosts=hosts
    )

    assert isinstance(result, NaabuScanOutputDTO)
    assert result.status == "completed"
    assert result.scanner == "naabu"
    assert result.targets_count == 2
    assert result.scan_mode == "passive"

    hosts = ["8.8.8.8"]
    nmap_cli = "nmap -sV -sC"

    async def mock_nmap(**kwargs):
        yield ProcessEvent(type="result", payload={"host": "8.8.8.8", "ip": "8.8.8.8", "port": 53, "protocol": "tcp"})
        yield ProcessEvent(type="result", payload={"host": "8.8.8.8", "ip": "8.8.8.8", "port": 80, "protocol": "tcp"})

    mock_runner.scan_with_nmap = mock_nmap

    async def mock_process(events, **kwargs):
        batch = [
            {"host": "8.8.8.8", "ip": "8.8.8.8", "port": 53, "protocol": "tcp"},
            {"host": "8.8.8.8", "ip": "8.8.8.8", "port": 80, "protocol": "tcp"}
        ]
        yield batch

    mock_processor.process = mock_process

    result = await naabu_service.execute_with_nmap(
        program_id=program_id,
        hosts=hosts,
        nmap_cli=nmap_cli,
        top_ports="100",
        rate=500
    )

    assert isinstance(result, NaabuScanOutputDTO)
    assert result.status == "completed"
    assert result.scanner == "naabu"
    assert result.targets_count == 1
    assert result.scan_mode == "nmap"


@pytest.mark.asyncio
async def test_event_bus_publish_active_scan(naabu_service, mock_runner, mock_processor, mock_event_bus, sample_naabu_results):
    """Test that results are published to EventBus for active scan"""
    program_id = UUID("123e4567-e89b-12d3-a456-426614174000")

    async def mock_scan(**kwargs):
        for result in sample_naabu_results:
            yield ProcessEvent(type="result", payload=result)

    mock_runner.scan = mock_scan

    async def mock_process(events, **kwargs):
        yield sample_naabu_results[:2]
        yield sample_naabu_results[2:]

    mock_processor.process = mock_process

    await naabu_service.execute(
        program_id=program_id,
        hosts=["8.8.8.8", "1.1.1.1"],
        top_ports="1000",
        rate=1000,
        scan_type="c",
        exclude_cdn=True
    )

    assert mock_event_bus.publish.call_count == 2

    first_call = mock_event_bus.publish.call_args_list[0]
    assert first_call[0][0] == EventType.NAABU_RESULTS_BATCH
    assert first_call[0][1]["program_id"] == str(program_id)
    assert first_call[0][1]["scan_mode"] == "active"
    assert first_call[0][1]["scan_type"] == "c"
    assert first_call[0][1]["ports"] == "top-1000"
    assert len(first_call[0][1]["results"]) == 2

    second_call = mock_event_bus.publish.call_args_list[1]
    assert second_call[0][0] == EventType.NAABU_RESULTS_BATCH
    assert len(second_call[0][1]["results"]) == 2


@pytest.mark.asyncio
async def test_event_bus_publish_passive_scan(naabu_service, mock_runner, mock_processor, mock_event_bus):
    """Test that results are published to EventBus for passive scan"""
    program_id = UUID("123e4567-e89b-12d3-a456-426614174000")

    async def mock_passive(**kwargs):
        yield ProcessEvent(type="result", payload={"host": "8.8.8.8", "ip": "8.8.8.8", "port": 53, "protocol": "tcp"})

    mock_runner.passive_scan = mock_passive

    async def mock_process(events, **kwargs):
        yield [{"host": "8.8.8.8", "ip": "8.8.8.8", "port": 53, "protocol": "tcp"}]

    mock_processor.process = mock_process

    await naabu_service.execute_passive(
        program_id=program_id,
        hosts=["8.8.8.8"]
    )

    mock_event_bus.publish.assert_called_once()
    call_args = mock_event_bus.publish.call_args[0]
    assert call_args[0] == EventType.NAABU_RESULTS_BATCH
    assert call_args[1]["scan_mode"] == "passive"
    assert "scan_type" not in call_args[1]


@pytest.mark.asyncio
async def test_event_bus_publish_nmap_scan(naabu_service, mock_runner, mock_processor, mock_event_bus):
    """Test that results are published to EventBus for nmap scan"""
    program_id = UUID("123e4567-e89b-12d3-a456-426614174000")

    async def mock_nmap(**kwargs):
        yield ProcessEvent(type="result", payload={"host": "8.8.8.8", "ip": "8.8.8.8", "port": 53, "protocol": "tcp"})

    mock_runner.scan_with_nmap = mock_nmap

    async def mock_process(events, **kwargs):
        yield [{"host": "8.8.8.8", "ip": "8.8.8.8", "port": 53, "protocol": "tcp"}]

    mock_processor.process = mock_process

    await naabu_service.execute_with_nmap(
        program_id=program_id,
        hosts=["8.8.8.8"],
        nmap_cli="nmap -sV",
        top_ports="1000",
        rate=1000
    )

    mock_event_bus.publish.assert_called_once()
    call_args = mock_event_bus.publish.call_args[0]
    assert call_args[0] == EventType.NAABU_RESULTS_BATCH
    assert call_args[1]["scan_mode"] == "nmap"
    assert call_args[1]["nmap_cli"] == "nmap -sV"
    assert call_args[1]["ports"] == "top-1000"


@pytest.mark.asyncio
async def test_no_results_found(naabu_service, mock_runner, mock_processor, mock_event_bus):
    """Test scan with no open ports found"""
    program_id = UUID("123e4567-e89b-12d3-a456-426614174000")

    async def mock_scan(**kwargs):
        return
        yield

    mock_runner.scan = mock_scan

    async def mock_process(events, **kwargs):
        return
        yield

    mock_processor.process = mock_process

    result = await naabu_service.execute(
        program_id=program_id,
        hosts=["192.168.1.1"],
        top_ports="1000",
        rate=1000,
        scan_type="c",
        exclude_cdn=True
    )

    assert result.status == "completed"
    assert "0 open ports" in result.message

    mock_event_bus.publish.assert_not_called()


@pytest.mark.asyncio
async def test_multiple_batches_published(naabu_service, mock_runner, mock_processor, mock_event_bus):
    """Test that multiple batches are published separately"""
    program_id = UUID("123e4567-e89b-12d3-a456-426614174000")

    async def mock_scan(**kwargs):
        for i in range(10):
            yield ProcessEvent(type="result", payload={"host": f"host{i}.com", "ip": f"1.1.1.{i}", "port": 80, "protocol": "tcp"})

    mock_runner.scan = mock_scan

    async def mock_process(events, **kwargs):
        yield [{"host": "host0.com", "ip": "1.1.1.0", "port": 80, "protocol": "tcp"}] * 5
        yield [{"host": "host5.com", "ip": "1.1.1.5", "port": 80, "protocol": "tcp"}] * 5

    mock_processor.process = mock_process

    result = await naabu_service.execute(
        program_id=program_id,
        hosts=["example.com"],
        top_ports="1000",
        rate=1000,
        scan_type="c",
        exclude_cdn=True
    )

    assert mock_event_bus.publish.call_count == 2
    assert "10 open ports" in result.message


@pytest.mark.asyncio
async def test_result_message_formatting(naabu_service, mock_runner, mock_processor, mock_event_bus):
    """Test result message formatting for different scenarios"""
    program_id = UUID("123e4567-e89b-12d3-a456-426614174000")

    async def mock_scan(**kwargs):
        yield ProcessEvent(type="result", payload={"host": "8.8.8.8", "ip": "8.8.8.8", "port": 53, "protocol": "tcp"})
        yield ProcessEvent(type="result", payload={"host": "8.8.8.8", "ip": "8.8.8.8", "port": 443, "protocol": "tcp"})
        yield ProcessEvent(type="result", payload={"host": "1.1.1.1", "ip": "1.1.1.1", "port": 80, "protocol": "tcp"})

    mock_runner.scan = mock_scan

    async def mock_process(events, **kwargs):
        yield [
            {"host": "8.8.8.8", "ip": "8.8.8.8", "port": 53, "protocol": "tcp"},
            {"host": "8.8.8.8", "ip": "8.8.8.8", "port": 443, "protocol": "tcp"},
            {"host": "1.1.1.1", "ip": "1.1.1.1", "port": 80, "protocol": "tcp"}
        ]

    mock_processor.process = mock_process

    result = await naabu_service.execute(
        program_id=program_id,
        hosts=["8.8.8.8", "1.1.1.1"],
        top_ports="1000",
        rate=1000,
        scan_type="c",
        exclude_cdn=True
    )

    assert result.message == "Active scan completed: 2 hosts, 3 open ports discovered"


@pytest.mark.asyncio
async def test_passive_scan_message(naabu_service, mock_runner, mock_processor, mock_event_bus):
    """Test result message for passive scan"""
    program_id = UUID("123e4567-e89b-12d3-a456-426614174000")

    async def mock_passive(**kwargs):
        yield ProcessEvent(type="result", payload={"host": "8.8.8.8", "ip": "8.8.8.8", "port": 53, "protocol": "tcp"})
        yield ProcessEvent(type="result", payload={"host": "8.8.8.8", "ip": "8.8.8.8", "port": 443, "protocol": "tcp"})

    mock_runner.passive_scan = mock_passive

    async def mock_process(events, **kwargs):
        yield [
            {"host": "8.8.8.8", "ip": "8.8.8.8", "port": 53, "protocol": "tcp"},
            {"host": "8.8.8.8", "ip": "8.8.8.8", "port": 443, "protocol": "tcp"}
        ]

    mock_processor.process = mock_process

    result = await naabu_service.execute_passive(
        program_id=program_id,
        hosts=["8.8.8.8"]
    )

    assert result.message == "Passive scan completed: 1 hosts, 2 ports discovered from Shodan"


@pytest.mark.asyncio
async def test_nmap_scan_message(naabu_service, mock_runner, mock_processor, mock_event_bus):
    """Test result message for nmap scan"""
    program_id = UUID("123e4567-e89b-12d3-a456-426614174000")

    async def mock_nmap(**kwargs):
        yield ProcessEvent(type="result", payload={"host": "8.8.8.8", "ip": "8.8.8.8", "port": 53, "protocol": "tcp"})

    mock_runner.scan_with_nmap = mock_nmap

    async def mock_process(events, **kwargs):
        yield [{"host": "8.8.8.8", "ip": "8.8.8.8", "port": 53, "protocol": "tcp"}]

    mock_processor.process = mock_process

    result = await naabu_service.execute_with_nmap(
        program_id=program_id,
        hosts=["8.8.8.8"],
        nmap_cli="nmap -sV",
        top_ports="1000",
        rate=1000
    )

    assert result.message == "Nmap scan completed: 1 hosts, 1 results with service detection"
