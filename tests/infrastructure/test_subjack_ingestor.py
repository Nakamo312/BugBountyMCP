from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from uuid import uuid4

import pytest

from api.infrastructure.ingestors.subjack_ingestor import (
    SUBDOMAIN_TAKEOVER_SIGNAL_TYPE,
    SUBDOMAIN_TAKEOVER_SIGNAL_VERSION,
    SubjackResultIngestor,
)


@dataclass
class FakeHost:
    id: object


class FakeHostsRepository:
    def __init__(self, host: FakeHost | None) -> None:
        self.host = host
        self.calls: list[dict[str, object]] = []

    async def get_by_fields(self, **filters):
        self.calls.append(filters)
        return self.host


class FakeResearchSignalsRepository:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    async def upsert_signal(self, **kwargs) -> None:
        self.records.append(kwargs)


class FakeUoW:
    def __init__(self, host: FakeHost | None = None) -> None:
        self.hosts = FakeHostsRepository(host)
        self.research_signals = FakeResearchSignalsRepository()


@pytest.mark.asyncio
async def test_subjack_records_research_signal_not_finding() -> None:
    program_id = uuid4()
    host_id = uuid4()
    uow = FakeUoW(FakeHost(id=host_id))
    ingestor = SubjackResultIngestor(
        uow=uow,
        settings=SimpleNamespace(HTTPX_INGESTOR_BATCH_SIZE=50),
    )

    await ingestor.process_record(
        uow,
        program_id,
        {
            "subdomain": "takeover.example.com",
            "service": "github",
            "vulnerable": True,
            "cname": "example.github.io",
        },
    )

    assert len(uow.research_signals.records) == 1
    signal = uow.research_signals.records[0]
    assert signal["program_id"] == program_id
    assert signal["signal_type"] == SUBDOMAIN_TAKEOVER_SIGNAL_TYPE
    assert signal["signal_version"] == SUBDOMAIN_TAKEOVER_SIGNAL_VERSION
    assert signal["asset_type"] == "host"
    assert signal["asset_id"] == str(host_id)
    assert signal["confidence"] == 0.65
    assert signal["payload_json"]["source_tool"] == "subjack"
    assert "Manual verification is required" in signal["payload_json"]["claim"]
    assert not hasattr(uow, "findings")
    assert not hasattr(uow, "vuln_types")


@pytest.mark.asyncio
async def test_subjack_skips_non_vulnerable_results() -> None:
    program_id = uuid4()
    uow = FakeUoW(FakeHost(id=uuid4()))
    ingestor = SubjackResultIngestor(
        uow=uow,
        settings=SimpleNamespace(HTTPX_INGESTOR_BATCH_SIZE=50),
    )

    await ingestor.process_record(
        uow,
        program_id,
        {
            "subdomain": "safe.example.com",
            "service": "github",
            "vulnerable": False,
        },
    )

    assert uow.research_signals.records == []
    assert uow.hosts.calls == []


@pytest.mark.asyncio
async def test_subjack_skips_signal_when_host_is_unknown() -> None:
    program_id = uuid4()
    uow = FakeUoW(host=None)
    ingestor = SubjackResultIngestor(
        uow=uow,
        settings=SimpleNamespace(HTTPX_INGESTOR_BATCH_SIZE=50),
    )

    await ingestor.process_record(
        uow,
        program_id,
        {
            "subdomain": "missing.example.com",
            "service": "github",
            "vulnerable": True,
        },
    )

    assert uow.research_signals.records == []
    assert uow.hosts.calls == [{"program_id": program_id, "host": "missing.example.com"}]


def test_subjack_signal_fingerprint_is_stable() -> None:
    program_id = uuid4()

    first = SubjackResultIngestor._fingerprint(
        program_id=program_id,
        subdomain="takeover.example.com",
        service="github",
        cname="example.github.io",
    )
    second = SubjackResultIngestor._fingerprint(
        program_id=program_id,
        subdomain="takeover.example.com",
        service="github",
        cname="example.github.io",
    )

    assert first == second
    assert len(first) == 64
