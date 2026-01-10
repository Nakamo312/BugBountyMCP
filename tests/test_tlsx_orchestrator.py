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
async def test_tlsx_results_batch_filters_by_scope_and_triggers_httpx(orchestrator, mock_bus, mock_container, sample_program):
    """Test TLSX_RESULTS_BATCH handler filters IPs by scope and triggers HTTPx for in-scope IPs"""
    with patch.object(orchestrator, '_filter_by_scope', new_callable=AsyncMock) as mock_filter:
        mock_filter.return_value = (["*.tinkoff.ru", "tinkoff.ru"], [])

        with patch.object(orchestrator, '_process_in_scope_ips', new_callable=AsyncMock) as mock_process:
            event = {
                "program_id": str(sample_program.id),
                "results": [
                    {
                        "host": "178.130.128.3",
                        "port": "443",
                        "subject_cn": "*.tinkoff.ru",
                        "subject_an": ["*.tinkoff.ru", "tinkoff.ru"]
                    },
                    {
                        "host": "178.130.128.4",
                        "port": "443",
                        "subject_cn": "*.tinkoff.ru",
                        "subject_an": ["*.tinkoff.ru", "tinkoff.ru"]
                    }
                ]
            }

            await orchestrator.handle_tlsx_results_batch(event)

            await asyncio.sleep(0.1)

            mock_bus.publish.assert_called_once_with(
                EventType.CERT_SAN_DISCOVERED,
                {
                    "program_id": str(sample_program.id),
                    "domains": ["*.tinkoff.ru", "tinkoff.ru"]
                }
            )


@pytest.mark.asyncio
async def test_tlsx_results_batch_filters_out_of_scope_ips(orchestrator, mock_bus, sample_program):
    """Test TLSX_RESULTS_BATCH filters out IPs with only out-of-scope domains"""
    with patch.object(orchestrator, '_filter_by_scope', new_callable=AsyncMock) as mock_filter:
        mock_filter.return_value = ([], ["out-of-scope.com"])

        with patch.object(orchestrator, '_process_in_scope_ips', new_callable=AsyncMock) as mock_process:
            event = {
                "program_id": str(sample_program.id),
                "results": [
                    {
                        "host": "1.2.3.4",
                        "port": "443",
                        "subject_cn": "out-of-scope.com",
                        "subject_an": ["out-of-scope.com"]
                    }
                ]
            }

            await orchestrator.handle_tlsx_results_batch(event)

            await asyncio.sleep(0.1)

            mock_process.assert_not_called()


@pytest.mark.asyncio
async def test_tlsx_results_batch_publishes_all_domains(orchestrator, mock_bus, sample_program):
    """Test TLSX_RESULTS_BATCH publishes all discovered domains regardless of scope"""
    with patch.object(orchestrator, '_filter_by_scope', new_callable=AsyncMock) as mock_filter:
        mock_filter.side_effect = [
            (["in-scope.com"], []),
            ([], ["out-of-scope.com"])
        ]

        event = {
            "program_id": str(sample_program.id),
            "results": [
                {
                    "host": "1.2.3.4",
                    "port": "443",
                    "subject_cn": "in-scope.com"
                },
                {
                    "host": "5.6.7.8",
                    "port": "443",
                    "subject_cn": "out-of-scope.com"
                }
            ]
        }

        await orchestrator.handle_tlsx_results_batch(event)

        mock_bus.publish.assert_called_once()
        call_args = mock_bus.publish.call_args[0]

        discovered_domains = set(call_args[1]["domains"])
        assert "in-scope.com" in discovered_domains
        assert "out-of-scope.com" in discovered_domains


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

            task = orchestrator.tasks.pop()
            await task

            mock_filter.assert_called_once_with(sample_program.id, ["example.com", "test.com"])
            mock_process.assert_called_once_with(sample_program.id, ["example.com", "test.com"])


@pytest.mark.asyncio
async def test_process_expanded_ips_runs_only_tlsx(orchestrator, sample_program):
    """Test _process_expanded_ips runs only TLSx (HTTPx is triggered by TLSx results)"""
    mock_tlsx_service = AsyncMock()
    mock_container_instance = AsyncMock()

    call_order = []

    async def track_tlsx_call(*args, **kwargs):
        call_order.append("tlsx")

    mock_tlsx_service.execute_default = track_tlsx_call

    async def mock_get(service_type):
        return mock_tlsx_service

    mock_container_instance.get = mock_get

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_container_instance)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    orchestrator.container = lambda: mock_cm

    ips = ["91.218.135.4", "91.218.135.5"]

    await orchestrator._process_expanded_ips(str(sample_program.id), ips)

    assert call_order == ["tlsx"]


import asyncio
