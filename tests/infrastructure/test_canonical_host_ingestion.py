from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

import pytest

from api.application.pipeline.canonical_processor import CanonicalBatchProcessor
from api.application.pipeline.records import HostFinding
from api.infrastructure.ingestors.canonical_router import CanonicalIngestorRouter
from api.infrastructure.ingestors.fuzz_finding_ingestor import FuzzFindingIngestor
from api.infrastructure.ingestors.host_finding_ingestor import HostFindingIngestor
from api.infrastructure.ingestors.host_ingestor import HostIngestor
from api.infrastructure.ingestors.javascript_reference_finding_ingestor import (
    JavaScriptReferenceFindingIngestor,
)
from api.infrastructure.ingestors.url_finding_ingestor import UrlFindingIngestor
from api.infrastructure.parsers.line_process_event_parsers import (
    Hakip2HostStdoutParser,
    SubfinderStdoutParser,
)
from api.infrastructure.schemas.models.process_event import ProcessEvent


@dataclass
class HostRow:
    id: object
    host: str


class FakeScopeRules:
    async def find_by_program(self, program_id):
        return []


class FakeHosts:
    def __init__(self) -> None:
        self.rows: dict[tuple[object, str], HostRow] = {}
        self.ensure_calls: list[tuple[object, str, bool]] = []

    async def get_by_fields(self, *, program_id, host):
        return self.rows.get((program_id, host))

    async def ensure(self, *, program_id, host, in_scope=True):
        self.ensure_calls.append((program_id, host, in_scope))
        return self.rows.setdefault((program_id, host), HostRow(uuid4(), host))


class FakeUow:
    def __init__(self) -> None:
        self.scope_rules = FakeScopeRules()
        self.hosts = FakeHosts()
        self.savepoints: list[str] = []
        self.released: list[str] = []
        self.commits = 0
        self.rollbacks = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def create_savepoint(self, name: str) -> None:
        self.savepoints.append(name)

    async def release_savepoint(self, name: str) -> None:
        self.released.append(name)

    async def rollback_to_savepoint(self, name: str) -> None:
        raise AssertionError("unexpected rollback")

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class SettingsStub:
    HOST_FINDING_BATCH_MIN = 2
    HOST_FINDING_BATCH_MAX = 2
    HOST_FINDING_BATCH_TIMEOUT = 100.0

    SUBFINDER_BATCH_MIN = 99
    SUBFINDER_BATCH_MAX = 99
    SUBFINDER_BATCH_TIMEOUT = 1.0


async def _events(*events: ProcessEvent):
    for event in events:
        yield event


@pytest.mark.asyncio
async def test_subfinder_parser_emits_host_finding_records() -> None:
    parser = SubfinderStdoutParser()

    records = [
        event
        async for event in parser.parse_stream(
            _events(ProcessEvent(type="stdout", payload='{"host":"a.example.com"}'))
        )
    ]

    assert records == [
        ProcessEvent(
            type="canonical_record",
            payload=HostFinding(
                host="a.example.com",
                source_tool="subfinder",
                raw='{"host":"a.example.com"}',
            ),
        )
    ]


@pytest.mark.asyncio
async def test_hakip2host_parser_emits_host_finding_with_ip_metadata() -> None:
    parser = Hakip2HostStdoutParser()

    records = [
        event
        async for event in parser.parse_stream(
            _events(ProcessEvent(type="stdout", payload="[PTR] 192.0.2.10 ptr.example.com"))
        )
    ]

    assert records == [
        ProcessEvent(
            type="canonical_record",
            payload=HostFinding(
                host="ptr.example.com",
                source_tool="hakip2host",
                ip="192.0.2.10",
                metadata={"method": "PTR"},
                raw="[PTR] 192.0.2.10 ptr.example.com",
            ),
        )
    ]


@pytest.mark.asyncio
async def test_canonical_processor_batches_only_canonical_records() -> None:
    processor = CanonicalBatchProcessor(SettingsStub())
    batches = [
        batch
        async for batch in processor.batch_stream(
            _events(
                ProcessEvent(type="stdout", payload="noise"),
                ProcessEvent(
                    type="canonical_record",
                    payload=HostFinding("a.example.com", "subfinder"),
                ),
                ProcessEvent(
                    type="canonical_record",
                    payload=HostFinding("b.example.com", "subfinder"),
                ),
            )
        )
    ]

    assert batches == [[
        HostFinding("a.example.com", "subfinder"),
        HostFinding("b.example.com", "subfinder"),
    ]]


@pytest.mark.asyncio
async def test_canonical_router_persists_host_findings_by_fact_type() -> None:
    program_id = uuid4()
    uow = FakeUow()
    router = CanonicalIngestorRouter(
        host_findings=HostFindingIngestor(uow=uow, settings=object()),  # type: ignore[arg-type]
        url_findings=UrlFindingIngestor(),
        javascript_references=JavaScriptReferenceFindingIngestor(),
        fuzz_findings=FuzzFindingIngestor(),
        service_findings=object(),  # type: ignore[arg-type]
    )

    result = await router.ingest(
        program_id,
        [
            HostFinding("a.example.com", "subfinder"),
            HostFinding("a.example.com", "hakip2host", ip="192.0.2.10"),
            HostFinding("b.example.com", "hakip2host", ip="192.0.2.11"),
        ],
    )

    assert result.raw_domains == ["a.example.com", "b.example.com"]
    assert uow.hosts.ensure_calls == [
        (program_id, "a.example.com", True),
        (program_id, "a.example.com", True),
        (program_id, "b.example.com", True),
    ]
    assert uow.commits == 1


def test_canonical_processor_uses_host_finding_batch_settings() -> None:
    processor = CanonicalBatchProcessor(SettingsStub())

    assert processor._get_batch_config(SettingsStub()) == {
        "min": 2,
        "max": 2,
        "timeout": 100.0,
    }


@pytest.mark.asyncio
async def test_host_finding_ingestor_rejects_legacy_payload_shape() -> None:
    program_id = uuid4()
    uow = FakeUow()
    ingestor = HostFindingIngestor(uow=uow, settings=object())  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="expects HostFinding"):
        await ingestor.process_record(
            uow,
            program_id,
            "legacy.example.com",  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_host_ingestor_keeps_legacy_payload_compatibility() -> None:
    program_id = uuid4()
    uow = FakeUow()
    ingestor = HostIngestor(uow=uow, settings=object())  # type: ignore[arg-type]

    result = await ingestor.ingest(
        program_id,
        [
            "legacy.example.com",
            {"hostname": "dict.example.com"},
        ],
    )

    assert result.raw_domains == ["legacy.example.com", "dict.example.com"]
    assert uow.hosts.ensure_calls == [
        (program_id, "legacy.example.com", True),
        (program_id, "dict.example.com", True),
    ]
