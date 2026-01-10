import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4, UUID

from api.application.services.orchestrator import Orchestrator
from api.infrastructure.events.event_types import EventType


@pytest.fixture
def mock_bus():
    bus = AsyncMock()
    bus.publish = AsyncMock()
    bus.connect = AsyncMock()
    bus.subscribe = AsyncMock()
    return bus


@pytest.fixture
def mock_container():
    container = AsyncMock()

    async def mock_context_manager():
        mock_request_container = AsyncMock()
        return mock_request_container

    container.return_value = mock_context_manager()

    return container


@pytest.fixture
def mock_settings():
    settings = AsyncMock()
    settings.ORCHESTRATOR_MAX_CONCURRENT = 5
    settings.ORCHESTRATOR_SCAN_DELAY = 1
    return settings


@pytest.fixture
def orchestrator(mock_bus, mock_container, mock_settings):
    return Orchestrator(
        bus=mock_bus,
        container=mock_container,
        settings=mock_settings
    )


@pytest.mark.asyncio
async def test_tlsx_results_batch_extracts_san_domains(orchestrator, mock_bus, sample_program):
    """Test TLSX_RESULTS_BATCH handler extracts SAN and CN domains"""
    event = {
        "program_id": str(sample_program.id),
        "results": [
            {
                "host": "178.130.128.3",
                "port": "443",
                "probe_status": True,
                "subject_cn": "*.tinkoff.ru",
                "subject_an": ["*.tinkoff.ru", "tinkoff.ru"]
            },
            {
                "host": "178.130.128.4",
                "port": "443",
                "probe_status": True,
                "subject_cn": "*.tinkoff.ru",
                "subject_an": ["*.tinkoff.ru", "tinkoff.ru"]
            }
        ]
    }

    await orchestrator.handle_tlsx_results_batch(event)

    mock_bus.publish.assert_called_once()
    call_args = mock_bus.publish.call_args
    assert call_args[0][0] == EventType.CERT_SAN_DISCOVERED
    assert call_args[0][1]["program_id"] == str(sample_program.id)

    discovered_domains = call_args[0][1]["domains"]
    assert "*.tinkoff.ru" in discovered_domains
    assert "tinkoff.ru" in discovered_domains
    assert len(discovered_domains) == 2


@pytest.mark.asyncio
async def test_tlsx_results_batch_handles_cn_only(orchestrator, mock_bus, sample_program):
    """Test TLSX_RESULTS_BATCH handler extracts CN when no SAN available"""
    event = {
        "program_id": str(sample_program.id),
        "results": [
            {
                "host": "91.218.135.4",
                "port": "443",
                "probe_status": True,
                "subject_cn": "t-access.ru"
            }
        ]
    }

    await orchestrator.handle_tlsx_results_batch(event)

    mock_bus.publish.assert_called_once()
    call_args = mock_bus.publish.call_args

    discovered_domains = call_args[0][1]["domains"]
    assert "t-access.ru" in discovered_domains
    assert len(discovered_domains) == 1


@pytest.mark.asyncio
async def test_tlsx_results_batch_deduplicates_domains(orchestrator, mock_bus, sample_program):
    """Test TLSX_RESULTS_BATCH handler deduplicates same domains from multiple certs"""
    event = {
        "program_id": str(sample_program.id),
        "results": [
            {
                "host": "178.130.128.3",
                "port": "443",
                "subject_cn": "example.com",
                "subject_an": ["example.com", "www.example.com"]
            },
            {
                "host": "178.130.128.4",
                "port": "443",
                "subject_cn": "example.com",
                "subject_an": ["example.com", "www.example.com"]
            },
            {
                "host": "178.130.128.5",
                "port": "443",
                "subject_cn": "test.com",
                "subject_an": ["test.com"]
            }
        ]
    }

    await orchestrator.handle_tlsx_results_batch(event)

    mock_bus.publish.assert_called_once()
    call_args = mock_bus.publish.call_args

    discovered_domains = call_args[0][1]["domains"]
    assert len(discovered_domains) == 3
    assert "example.com" in discovered_domains
    assert "www.example.com" in discovered_domains
    assert "test.com" in discovered_domains


@pytest.mark.asyncio
async def test_tlsx_results_batch_skips_empty_results(orchestrator, mock_bus, sample_program):
    """Test TLSX_RESULTS_BATCH handler handles results without SAN/CN"""
    event = {
        "program_id": str(sample_program.id),
        "results": [
            {
                "host": "178.130.128.3",
                "port": "443",
                "probe_status": False
            },
            {
                "host": "178.130.128.4",
                "port": "443",
                "probe_status": True,
                "subject_an": []
            }
        ]
    }

    await orchestrator.handle_tlsx_results_batch(event)

    mock_bus.publish.assert_not_called()


@pytest.mark.asyncio
async def test_cert_san_discovered_triggers_dnsx(orchestrator, sample_program):
    """Test CERT_SAN_DISCOVERED event triggers DNSx validation"""
    with patch.object(orchestrator, '_filter_by_scope', new_callable=AsyncMock) as mock_filter:
        with patch.object(orchestrator, '_process_cert_san_domains', new_callable=AsyncMock) as mock_process:
            mock_filter.return_value = (["example.com", "test.com"], [])

            event = {
                "program_id": str(sample_program.id),
                "domains": ["example.com", "test.com"]
            }

            await orchestrator.handle_cert_san_discovered(event)

            # Wait for background task
            task = orchestrator.tasks.pop()
            await task

            mock_filter.assert_called_once_with(sample_program.id, ["example.com", "test.com"])
            mock_process.assert_called_once_with(sample_program.id, ["example.com", "test.com"])


@pytest.mark.asyncio
async def test_cert_san_discovered_filters_out_of_scope(orchestrator, sample_program):
    """Test CERT_SAN_DISCOVERED filters out-of-scope domains"""
    with patch.object(orchestrator, '_filter_by_scope', new_callable=AsyncMock) as mock_filter:
        with patch.object(orchestrator, '_process_cert_san_domains', new_callable=AsyncMock) as mock_process:
            mock_filter.return_value = (
                ["example.com"],
                ["out-of-scope.com", "another-out.com"]
            )

            event = {
                "program_id": str(sample_program.id),
                "domains": ["example.com", "out-of-scope.com", "another-out.com"]
            }

            await orchestrator.handle_cert_san_discovered(event)

            # Wait for background task
            task = orchestrator.tasks.pop()
            await task

            mock_process.assert_called_once_with(sample_program.id, ["example.com"])


@pytest.mark.asyncio
async def test_cert_san_discovered_no_in_scope_domains(orchestrator, sample_program):
    """Test CERT_SAN_DISCOVERED with all domains out of scope"""
    with patch.object(orchestrator, '_filter_by_scope', new_callable=AsyncMock) as mock_filter:
        with patch.object(orchestrator, '_process_cert_san_domains', new_callable=AsyncMock) as mock_process:
            mock_filter.return_value = ([], ["out-of-scope.com"])

            event = {
                "program_id": str(sample_program.id),
                "domains": ["out-of-scope.com"]
            }

            await orchestrator.handle_cert_san_discovered(event)

            mock_process.assert_not_called()


@pytest.mark.asyncio
async def test_process_cert_san_domains_calls_dnsx(orchestrator, sample_program):
    """Test _process_cert_san_domains triggers DNSx basic validation"""
    mock_dnsx_service = AsyncMock()
    mock_container_instance = AsyncMock()
    mock_container_instance.get.return_value = mock_dnsx_service

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_container_instance)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    orchestrator.container = lambda: mock_cm

    domains = ["example.com", "test.com"]

    await orchestrator._process_cert_san_domains(sample_program.id, domains)

    mock_dnsx_service.execute_basic.assert_called_once_with(
        program_id=sample_program.id,
        targets=domains
    )


@pytest.mark.asyncio
async def test_process_expanded_ips_runs_tlsx_then_httpx(orchestrator, sample_program):
    """Test _process_expanded_ips runs TLSx scan before HTTPx"""
    mock_tlsx_service = AsyncMock()
    mock_httpx_service = AsyncMock()
    mock_container_instance = AsyncMock()

    call_order = []

    async def track_tlsx_call(*args, **kwargs):
        call_order.append("tlsx")

    async def track_httpx_call(*args, **kwargs):
        call_order.append("httpx")

    mock_tlsx_service.execute_default = track_tlsx_call
    mock_httpx_service.execute = track_httpx_call

    async def mock_get(service_type):
        if "TLSx" in str(service_type):
            return mock_tlsx_service
        return mock_httpx_service

    mock_container_instance.get = mock_get

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_container_instance)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    orchestrator.container = lambda: mock_cm

    ips = ["91.218.135.4", "91.218.135.5"]

    await orchestrator._process_expanded_ips(str(sample_program.id), ips)

    assert call_order == ["tlsx", "httpx"]
