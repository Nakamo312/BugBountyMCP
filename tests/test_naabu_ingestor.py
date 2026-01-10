"""Tests for Naabu Result Ingestor"""

import pytest
from uuid import UUID, uuid4
from unittest.mock import AsyncMock, MagicMock

from api.infrastructure.ingestors.naabu_ingestor import NaabuResultIngestor
from api.domain.models import IPAddressModel, ServiceModel
from api.config import Settings


@pytest.fixture
def mock_uow():
    uow = AsyncMock()
    uow.ip_addresses = AsyncMock()
    uow.services = AsyncMock()
    uow.commit = AsyncMock()
    uow.rollback = AsyncMock()
    uow.create_savepoint = AsyncMock()
    uow.release_savepoint = AsyncMock()
    uow.rollback_to_savepoint = AsyncMock()
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock()
    return uow


@pytest.fixture
def mock_settings():
    settings = MagicMock(spec=Settings)
    settings.NAABU_INGESTOR_BATCH_SIZE = 100
    return settings


@pytest.fixture
def naabu_ingestor(mock_settings):
    mock_uow = MagicMock()
    mock_uow.ip_addresses = MagicMock()
    mock_uow.services = MagicMock()
    mock_uow.commit = AsyncMock()
    mock_uow.rollback = AsyncMock()
    mock_uow.create_savepoint = AsyncMock()
    mock_uow.release_savepoint = AsyncMock()
    mock_uow.rollback_to_savepoint = AsyncMock()
    mock_uow.__aenter__ = AsyncMock(return_value=mock_uow)
    mock_uow.__aexit__ = AsyncMock(return_value=None)

    ingestor = NaabuResultIngestor(uow=mock_uow, settings=mock_settings)
    return ingestor


@pytest.fixture
def sample_naabu_results():
    return [
        {"host": "8.8.8.8", "ip": "8.8.8.8", "port": 53, "protocol": "tcp"},
        {"host": "8.8.8.8", "ip": "8.8.8.8", "port": 443, "protocol": "tcp"},
        {"host": "1.1.1.1", "ip": "1.1.1.1", "port": 80, "protocol": "tcp"},
        {"host": "1.1.1.1", "ip": "1.1.1.1", "port": 443, "protocol": "tcp"},
    ]


@pytest.mark.asyncio
async def test_ingest_success(naabu_ingestor, sample_naabu_results):
    """Test successful ingestion of Naabu results"""
    program_id = UUID("123e4567-e89b-12d3-a456-426614174000")
    mock_uow = naabu_ingestor.uow

    ip_8888 = MagicMock()
    ip_8888.id = uuid4()
    ip_1111 = MagicMock()
    ip_1111.id = uuid4()

    async def mock_ensure_ip(model, unique_fields):
        if model.address == "8.8.8.8":
            return ip_8888
        return ip_1111

    mock_uow.ip_addresses.ensure = AsyncMock(side_effect=mock_ensure_ip)
    mock_uow.services.ensure = AsyncMock()

    await naabu_ingestor.ingest(sample_naabu_results, program_id)

    assert mock_uow.ip_addresses.ensure.call_count == 4
    assert mock_uow.services.ensure.call_count == 4
    mock_uow.commit.assert_called_once()


@pytest.mark.asyncio
async def test_ingest_creates_ip_addresses(naabu_ingestor):
    """Test that IP addresses are created correctly"""
    program_id = UUID("123e4567-e89b-12d3-a456-426614174000")
    mock_uow = naabu_ingestor.uow
    results = [
        {"host": "8.8.8.8", "ip": "8.8.8.8", "port": 53, "protocol": "tcp"},
    ]

    ip_obj = MagicMock()
    ip_obj.id = uuid4()
    mock_uow.ip_addresses.ensure = AsyncMock(return_value=ip_obj)
    mock_uow.services.ensure = AsyncMock()

    await naabu_ingestor.ingest(results, program_id)

    call_args = mock_uow.ip_addresses.ensure.call_args
    ip_model = call_args[0][0]
    assert isinstance(ip_model, IPAddressModel)
    assert ip_model.address == "8.8.8.8"
    assert ip_model.program_id == program_id
    assert call_args[1]["unique_fields"] == ["address", "program_id"]


@pytest.mark.asyncio
async def test_ingest_creates_services(naabu_ingestor):
    """Test that services are created correctly"""
    mock_uow = naabu_ingestor.uow
    program_id = UUID("123e4567-e89b-12d3-a456-426614174000")
    results = [
        {"host": "8.8.8.8", "ip": "8.8.8.8", "port": 53, "protocol": "tcp"},
    ]

    ip_obj = MagicMock()
    ip_obj.id = uuid4()
    mock_uow.ip_addresses.ensure = AsyncMock(return_value=ip_obj)
    mock_uow.services.ensure = AsyncMock()

    await naabu_ingestor.ingest(results, program_id)

    call_kwargs = mock_uow.services.ensure.call_args[1]
    assert call_kwargs["ip_id"] == ip_obj.id
    assert call_kwargs["port"] == 53
    assert call_kwargs["scheme"] == "http"  # Port 53 maps to http
    assert call_kwargs["technologies"] == {}


@pytest.mark.asyncio
async def test_ingest_batching(naabu_ingestor):
    """Test that results are processed in batches"""
    mock_uow = naabu_ingestor.uow
    program_id = UUID("123e4567-e89b-12d3-a456-426614174000")
    naabu_ingestor.batch_size = 2

    results = [
        {"host": "8.8.8.8", "ip": "8.8.8.8", "port": 53, "protocol": "tcp"},
        {"host": "8.8.8.8", "ip": "8.8.8.8", "port": 443, "protocol": "tcp"},
        {"host": "1.1.1.1", "ip": "1.1.1.1", "port": 80, "protocol": "tcp"},
        {"host": "1.1.1.1", "ip": "1.1.1.1", "port": 443, "protocol": "tcp"},
    ]

    ip_obj = MagicMock()
    ip_obj.id = uuid4()
    mock_uow.ip_addresses.ensure = AsyncMock(return_value=ip_obj)
    mock_uow.services.ensure = AsyncMock()

    await naabu_ingestor.ingest(results, program_id)

    assert mock_uow.create_savepoint.call_count == 2
    assert mock_uow.release_savepoint.call_count == 2
    mock_uow.create_savepoint.assert_any_call("naabu_batch_0")
    mock_uow.create_savepoint.assert_any_call("naabu_batch_1")


@pytest.mark.asyncio
async def test_ingest_savepoint_rollback_on_error(naabu_ingestor):
    """Test that individual item errors are caught and skipped, not causing batch rollback"""
    mock_uow = naabu_ingestor.uow
    program_id = UUID("123e4567-e89b-12d3-a456-426614174000")
    naabu_ingestor.batch_size = 2

    results = [
        {"host": "8.8.8.8", "ip": "8.8.8.8", "port": 53, "protocol": "tcp"},
        {"host": "8.8.8.8", "ip": "8.8.8.8", "port": 443, "protocol": "tcp"},
        {"host": "1.1.1.1", "ip": "1.1.1.1", "port": 80, "protocol": "tcp"},
    ]

    ip_obj = MagicMock()
    ip_obj.id = uuid4()

    call_count = 0

    async def mock_ensure_ip(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise Exception("Database error")
        return ip_obj

    mock_uow.ip_addresses.ensure = AsyncMock(side_effect=mock_ensure_ip)
    mock_uow.services.ensure = AsyncMock()

    await naabu_ingestor.ingest(results, program_id)

    # Individual item errors are caught, so no rollback happens
    assert mock_uow.rollback_to_savepoint.call_count == 0
    # But the batch completes successfully
    assert mock_uow.release_savepoint.call_count == 2
    mock_uow.commit.assert_called_once()


@pytest.mark.asyncio
async def test_ingest_partial_batch_failure(naabu_ingestor):
    """Test that failed batches don't prevent successful batches from committing"""
    mock_uow = naabu_ingestor.uow
    program_id = UUID("123e4567-e89b-12d3-a456-426614174000")
    naabu_ingestor.batch_size = 2

    results = [
        {"host": "8.8.8.8", "ip": "8.8.8.8", "port": 53, "protocol": "tcp"},
        {"host": "8.8.8.8", "ip": "8.8.8.8", "port": 443, "protocol": "tcp"},
        {"host": "1.1.1.1", "ip": "1.1.1.1", "port": 80, "protocol": "tcp"},
        {"host": "1.1.1.1", "ip": "1.1.1.1", "port": 443, "protocol": "tcp"},
    ]

    ip_obj = MagicMock()
    ip_obj.id = uuid4()

    call_count = 0

    async def mock_ensure_ip(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 4:
            raise Exception("Database error")
        return ip_obj

    mock_uow.ip_addresses.ensure = AsyncMock(side_effect=mock_ensure_ip)
    mock_uow.services.ensure = AsyncMock()

    await naabu_ingestor.ingest(results, program_id)

    # Individual item errors don't cause batch rollback
    # Both batches complete successfully
    assert mock_uow.release_savepoint.call_count == 2
    assert mock_uow.rollback_to_savepoint.call_count == 0
    mock_uow.commit.assert_called_once()


@pytest.mark.asyncio
async def test_ingest_empty_results(naabu_ingestor):
    """Test ingestion with empty results list"""
    mock_uow = naabu_ingestor.uow
    program_id = UUID("123e4567-e89b-12d3-a456-426614174000")

    await naabu_ingestor.ingest([], program_id)

    mock_uow.ip_addresses.ensure.assert_not_called()
    mock_uow.services.ensure.assert_not_called()
    mock_uow.commit.assert_not_called()


@pytest.mark.asyncio
async def test_ingest_missing_ip_field(naabu_ingestor):
    """Test that results missing IP field are skipped"""
    mock_uow = naabu_ingestor.uow
    program_id = UUID("123e4567-e89b-12d3-a456-426614174000")
    results = [
        {"host": "8.8.8.8", "port": 53, "protocol": "tcp"},
        {"host": "1.1.1.1", "ip": "1.1.1.1", "port": 80, "protocol": "tcp"},
    ]

    ip_obj = MagicMock()
    ip_obj.id = uuid4()
    mock_uow.ip_addresses.ensure = AsyncMock(return_value=ip_obj)
    mock_uow.services.ensure = AsyncMock()

    await naabu_ingestor.ingest(results, program_id)

    assert mock_uow.ip_addresses.ensure.call_count == 1
    assert mock_uow.services.ensure.call_count == 1


@pytest.mark.asyncio
async def test_ingest_missing_port_field(naabu_ingestor):
    """Test that results missing port field are skipped"""
    mock_uow = naabu_ingestor.uow
    program_id = UUID("123e4567-e89b-12d3-a456-426614174000")
    results = [
        {"host": "8.8.8.8", "ip": "8.8.8.8", "protocol": "tcp"},
        {"host": "1.1.1.1", "ip": "1.1.1.1", "port": 80, "protocol": "tcp"},
    ]

    ip_obj = MagicMock()
    ip_obj.id = uuid4()
    mock_uow.ip_addresses.ensure = AsyncMock(return_value=ip_obj)
    mock_uow.services.ensure = AsyncMock()

    await naabu_ingestor.ingest(results, program_id)

    assert mock_uow.ip_addresses.ensure.call_count == 1
    assert mock_uow.services.ensure.call_count == 1


@pytest.mark.asyncio
async def test_ingest_default_protocol(naabu_ingestor):
    """Test that protocol defaults to tcp if missing"""
    mock_uow = naabu_ingestor.uow
    program_id = UUID("123e4567-e89b-12d3-a456-426614174000")
    results = [
        {"host": "8.8.8.8", "ip": "8.8.8.8", "port": 53},
    ]

    ip_obj = MagicMock()
    ip_obj.id = uuid4()
    mock_uow.ip_addresses.ensure = AsyncMock(return_value=ip_obj)
    mock_uow.services.ensure = AsyncMock()

    await naabu_ingestor.ingest(results, program_id)

    call_kwargs = mock_uow.services.ensure.call_args[1]
    # When protocol is missing, we still map port to scheme (http for port 53)
    assert call_kwargs["scheme"] == "http"


@pytest.mark.asyncio
async def test_ingest_multiple_ips(naabu_ingestor, sample_naabu_results):
    """Test that multiple unique IPs are created"""
    mock_uow = naabu_ingestor.uow
    program_id = UUID("123e4567-e89b-12d3-a456-426614174000")

    created_ips = {}

    async def mock_ensure_ip(model, unique_fields):
        if model.address not in created_ips:
            ip_obj = MagicMock()
            ip_obj.id = uuid4()
            created_ips[model.address] = ip_obj
        return created_ips[model.address]

    mock_uow.ip_addresses.ensure = AsyncMock(side_effect=mock_ensure_ip)
    mock_uow.services.ensure = AsyncMock()

    await naabu_ingestor.ingest(sample_naabu_results, program_id)

    assert len(created_ips) == 2
    assert "8.8.8.8" in created_ips
    assert "1.1.1.1" in created_ips


@pytest.mark.asyncio
async def test_ingest_multiple_ports_same_ip(naabu_ingestor):
    """Test that multiple ports on same IP create separate services"""
    mock_uow = naabu_ingestor.uow
    program_id = UUID("123e4567-e89b-12d3-a456-426614174000")
    results = [
        {"host": "8.8.8.8", "ip": "8.8.8.8", "port": 53, "protocol": "tcp"},
        {"host": "8.8.8.8", "ip": "8.8.8.8", "port": 80, "protocol": "tcp"},
        {"host": "8.8.8.8", "ip": "8.8.8.8", "port": 443, "protocol": "tcp"},
    ]

    ip_obj = MagicMock()
    ip_obj.id = uuid4()
    mock_uow.ip_addresses.ensure = AsyncMock(return_value=ip_obj)
    mock_uow.services.ensure = AsyncMock()

    await naabu_ingestor.ingest(results, program_id)

    assert mock_uow.ip_addresses.ensure.call_count == 3
    assert mock_uow.services.ensure.call_count == 3

    service_calls = mock_uow.services.ensure.call_args_list
    ports = [call[1]["port"] for call in service_calls]
    assert sorted(ports) == [53, 80, 443]


@pytest.mark.asyncio
async def test_ingest_udp_protocol(naabu_ingestor):
    """Test ingestion of UDP protocol services"""
    mock_uow = naabu_ingestor.uow
    program_id = UUID("123e4567-e89b-12d3-a456-426614174000")
    results = [
        {"host": "8.8.8.8", "ip": "8.8.8.8", "port": 53, "protocol": "udp"},
    ]

    ip_obj = MagicMock()
    ip_obj.id = uuid4()
    mock_uow.ip_addresses.ensure = AsyncMock(return_value=ip_obj)
    mock_uow.services.ensure = AsyncMock()

    await naabu_ingestor.ingest(results, program_id)

    call_kwargs = mock_uow.services.ensure.call_args[1]
    # UDP port 53 still maps to http scheme
    assert call_kwargs["scheme"] == "http"


@pytest.mark.asyncio
async def test_ingest_large_batch(naabu_ingestor):
    """Test ingestion of large result set"""
    mock_uow = naabu_ingestor.uow
    program_id = UUID("123e4567-e89b-12d3-a456-426614174000")
    naabu_ingestor.batch_size = 50

    results = [
        {"host": f"host{i}.com", "ip": f"192.168.1.{i % 255}", "port": 80 + (i % 100), "protocol": "tcp"}
        for i in range(250)
    ]

    ip_obj = MagicMock()
    ip_obj.id = uuid4()
    mock_uow.ip_addresses.ensure = AsyncMock(return_value=ip_obj)
    mock_uow.services.ensure = AsyncMock()

    await naabu_ingestor.ingest(results, program_id)

    assert mock_uow.create_savepoint.call_count == 5
    assert mock_uow.release_savepoint.call_count == 5
    assert mock_uow.ip_addresses.ensure.call_count == 250
    assert mock_uow.services.ensure.call_count == 250
    mock_uow.commit.assert_called_once()


@pytest.mark.asyncio
async def test_ingest_ensures_idempotency(naabu_ingestor):
    """Test that ensure() is used for idempotent operations"""
    mock_uow = naabu_ingestor.uow
    program_id = UUID("123e4567-e89b-12d3-a456-426614174000")
    results = [
        {"host": "8.8.8.8", "ip": "8.8.8.8", "port": 53, "protocol": "tcp"},
    ]

    ip_obj = MagicMock()
    ip_obj.id = uuid4()
    mock_uow.ip_addresses.ensure = AsyncMock(return_value=ip_obj)
    mock_uow.services.ensure = AsyncMock()

    await naabu_ingestor.ingest(results, program_id)

    mock_uow.ip_addresses.ensure.assert_called_once()
    assert mock_uow.ip_addresses.ensure.call_args[1]["unique_fields"] == ["address", "program_id"]

    mock_uow.services.ensure.assert_called_once()
    # Services.ensure is called with keyword args, not unique_fields
    assert "ip_id" in mock_uow.services.ensure.call_args[1]
    assert "port" in mock_uow.services.ensure.call_args[1]
    assert "scheme" in mock_uow.services.ensure.call_args[1]
