import pytest
from unittest.mock import AsyncMock
from uuid import uuid4

from api.infrastructure.ingestors.dnsx_ingestor import DNSxResultIngestor
from api.domain.models import HostModel, DNSRecordModel


@pytest.fixture
def dnsx_uow():
    uow = AsyncMock()

    uow.hosts = AsyncMock()
    uow.dns_records = AsyncMock()

    uow.commit = AsyncMock()
    uow.rollback = AsyncMock()
    uow.create_savepoint = AsyncMock()
    uow.rollback_to_savepoint = AsyncMock()
    uow.release_savepoint = AsyncMock()

    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=None)

    return uow


@pytest.fixture
def mock_bus():
    bus = AsyncMock()
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def settings():
    settings = AsyncMock()
    settings.DNSX_INGESTOR_BATCH_SIZE = 100
    return settings


@pytest.fixture
def dnsx_ingestor(dnsx_uow, settings):
    return DNSxResultIngestor(dnsx_uow, settings)


@pytest.mark.asyncio
async def test_ingest_basic_dns_records(dnsx_ingestor, dnsx_uow, sample_program, sample_host):
    """Test ingesting basic DNS records (A, AAAA, CNAME)"""
    dnsx_uow.hosts.get_by_fields.return_value = sample_host

    results = [
        {
            "host": "example.com",
            "a": ["1.2.3.4", "5.6.7.8"],
            "aaaa": ["2001:db8::1"],
            "cname": ["www.example.com"],
            "wildcard": False
        }
    ]

    await dnsx_ingestor.ingest(sample_program.id, results)

    assert dnsx_uow.dns_records.ensure.call_count == 4  # 2 A + 1 AAAA + 1 CNAME
    assert dnsx_uow.commit.called


@pytest.mark.asyncio
async def test_ingest_deep_dns_records(dnsx_ingestor, dnsx_uow, sample_program, sample_host):
    """Test ingesting deep DNS records (MX, TXT, NS, SOA)"""
    dnsx_uow.hosts.get_by_fields.return_value = sample_host

    results = [
        {
            "host": "example.com",
            "a": ["1.2.3.4"],
            "mx": ["mail.example.com"],
            "txt": ["v=spf1 include:_spf.google.com ~all"],
            "ns": ["ns1.example.com", "ns2.example.com"],
            "soa": [
                {
                    "ns": "ns1.example.com",
                    "mailbox": "admin.example.com",
                    "serial": 2025010401,
                    "refresh": 900,
                    "retry": 300,
                    "expire": 1728000,
                    "minttl": 86400
                }
            ],
            "wildcard": False
        }
    ]

    await dnsx_ingestor.ingest(sample_program.id, results)

    # 1 A + 1 MX + 1 TXT + 2 NS + 1 SOA = 6
    assert dnsx_uow.dns_records.ensure.call_count == 6
    assert dnsx_uow.commit.called


@pytest.mark.asyncio
async def test_ingest_wildcard_flag(dnsx_ingestor, dnsx_uow, sample_program, sample_host):
    """Test wildcard flag is preserved"""
    dnsx_uow.hosts.get_by_fields.return_value = sample_host

    results = [
        {
            "host": "random123.example.com",
            "a": ["1.2.3.4"],
            "wildcard": True
        }
    ]

    await dnsx_ingestor.ingest(sample_program.id, results)

    ensure_call = dnsx_uow.dns_records.ensure.call_args
    assert ensure_call[1]["is_wildcard"] is True


@pytest.mark.asyncio
async def test_ingest_soa_as_string(dnsx_ingestor, dnsx_uow, sample_program, sample_host):
    """Test SOA record when returned as string instead of dict"""
    dnsx_uow.hosts.get_by_fields.return_value = sample_host

    results = [
        {
            "host": "example.com",
            "soa": ["ns1.example.com admin.example.com 2025010401 900 300 1728000 86400"],
            "wildcard": False
        }
    ]

    await dnsx_ingestor.ingest(sample_program.id, results)

    ensure_call = dnsx_uow.dns_records.ensure.call_args
    assert ensure_call[1]["record_type"] == "SOA"
    assert isinstance(ensure_call[1]["value"], str)


@pytest.mark.asyncio
async def test_ingest_host_not_found(dnsx_ingestor, dnsx_uow, sample_program):
    """Test handling of DNS records for non-existent host"""
    dnsx_uow.hosts.get_by_fields.return_value = None

    results = [
        {
            "host": "nonexistent.com",
            "a": ["1.2.3.4"],
            "wildcard": False
        }
    ]

    await dnsx_ingestor.ingest(sample_program.id, results)

    # Should not call ensure since host not found
    dnsx_uow.dns_records.ensure.assert_not_called()


@pytest.mark.asyncio
async def test_ingest_batching(dnsx_ingestor, dnsx_uow, sample_program, sample_host):
    """Test results are processed in batches"""
    dnsx_uow.hosts.get_by_fields.return_value = sample_host

    # Create 150 results (batch size is 100)
    results = [
        {
            "host": f"host{i}.example.com",
            "a": ["1.2.3.4"],
            "wildcard": False
        }
        for i in range(150)
    ]

    await dnsx_ingestor.ingest(sample_program.id, results)

    # Should create 2 savepoints (2 batches)
    assert dnsx_uow.create_savepoint.call_count == 2
    assert dnsx_uow.release_savepoint.call_count == 2


@pytest.mark.asyncio
async def test_ingest_rollback_on_error(dnsx_ingestor, dnsx_uow, sample_program, sample_host):
    """Test rollback to savepoint on batch error"""
    dnsx_uow.hosts.get_by_fields.return_value = sample_host
    dnsx_uow.dns_records.ensure.side_effect = [None, Exception("DB error"), None]

    results = [
        {"host": "host1.com", "a": ["1.2.3.4"], "wildcard": False},
        {"host": "host2.com", "a": ["5.6.7.8"], "wildcard": False},
        {"host": "host3.com", "a": ["9.10.11.12"], "wildcard": False},
    ]

    await dnsx_ingestor.ingest(sample_program.id, results)

    # Should rollback the failed batch
    assert dnsx_uow.rollback_to_savepoint.called


@pytest.mark.asyncio
async def test_ingest_empty_results(dnsx_ingestor, dnsx_uow, sample_program):
    """Test handling empty results"""
    results = []

    await dnsx_ingestor.ingest(sample_program.id, results)

    dnsx_uow.dns_records.ensure.assert_not_called()
    dnsx_uow.commit.assert_called_once()


@pytest.mark.asyncio
async def test_ingest_multiple_record_types(dnsx_ingestor, dnsx_uow, sample_program, sample_host):
    """Test ingesting all record types at once"""
    dnsx_uow.hosts.get_by_fields.return_value = sample_host

    results = [
        {
            "host": "example.com",
            "a": ["1.2.3.4"],
            "aaaa": ["2001:db8::1"],
            "cname": ["www.example.com"],
            "mx": ["mail.example.com"],
            "txt": ["v=spf1 ~all", "google-site-verification=xyz"],
            "ns": ["ns1.example.com"],
            "soa": [{"ns": "ns1.example.com", "mailbox": "admin.example.com", "serial": 1}],
            "ptr": ["ptr.example.com"],
            "wildcard": False
        }
    ]

    await dnsx_ingestor.ingest(sample_program.id, results)

    # 1 A + 1 AAAA + 1 CNAME + 1 MX + 2 TXT + 1 NS + 1 SOA + 1 PTR = 9
    assert dnsx_uow.dns_records.ensure.call_count == 9
