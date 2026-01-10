"""Tests for Naabu Orchestrator Integration"""

import pytest
import asyncio
from uuid import UUID
from unittest.mock import AsyncMock, MagicMock, patch

from api.application.services.orchestrator import Orchestrator
from api.infrastructure.events.event_types import EventType
from api.config import Settings


@pytest.fixture
def mock_event_bus():
    bus = AsyncMock()
    bus.connect = AsyncMock()
    bus.subscribe = AsyncMock()
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def mock_container():
    container = MagicMock()
    return container


@pytest.fixture
def mock_settings():
    settings = MagicMock(spec=Settings)
    settings.ORCHESTRATOR_MAX_CONCURRENT = 2
    settings.ORCHESTRATOR_SCAN_DELAY = 0
    return settings


@pytest.fixture
def orchestrator(mock_event_bus, mock_container, mock_settings):
    return Orchestrator(
        bus=mock_event_bus,
        container=mock_container,
        settings=mock_settings
    )


@pytest.mark.asyncio
async def test_handle_naabu_results_batch_ingests_results(orchestrator, mock_container):
    """Test that Naabu results batch is ingested correctly"""
    event = {
        "program_id": "123e4567-e89b-12d3-a456-426614174000",
        "results": [
            {"host": "8.8.8.8", "ip": "8.8.8.8", "port": 53, "protocol": "tcp"},
            {"host": "8.8.8.8", "ip": "8.8.8.8", "port": 443, "protocol": "tcp"},
        ],
        "scan_mode": "active"
    }

    mock_ingestor = AsyncMock()
    mock_ingestor.ingest = AsyncMock()

    mock_request_container = AsyncMock()
    mock_request_container.__aenter__ = AsyncMock(return_value=mock_request_container)
    mock_request_container.__aexit__ = AsyncMock(return_value=None)
    mock_request_container.get = AsyncMock(return_value=mock_ingestor)

    mock_container.return_value = mock_request_container

    await orchestrator.handle_naabu_results_batch(event)

    mock_ingestor.ingest.assert_called_once_with(
        event["results"],
        UUID(event["program_id"])
    )


@pytest.mark.asyncio
async def test_handle_naabu_results_batch_error_handling(orchestrator, mock_container):
    """Test error handling in Naabu results batch processing"""
    event = {
        "program_id": "123e4567-e89b-12d3-a456-426614174000",
        "results": [
            {"host": "8.8.8.8", "ip": "8.8.8.8", "port": 53, "protocol": "tcp"},
        ],
        "scan_mode": "active"
    }

    mock_ingestor = AsyncMock()
    mock_ingestor.ingest = AsyncMock(side_effect=Exception("Ingestion error"))

    mock_request_container = AsyncMock()
    mock_request_container.__aenter__ = AsyncMock(return_value=mock_request_container)
    mock_request_container.__aexit__ = AsyncMock(return_value=None)
    mock_request_container.get = AsyncMock(return_value=mock_ingestor)

    mock_container.return_value = mock_request_container

    await orchestrator.handle_naabu_results_batch(event)

    mock_ingestor.ingest.assert_called_once()
