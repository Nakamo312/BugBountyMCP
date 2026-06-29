from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from api.application.pipeline.canonical_processor import ServiceFindingBatchProcessor
from api.application.pipeline.records import ServiceFinding
from api.infrastructure.ingestors.canonical_router import CanonicalIngestorRouter
from api.infrastructure.ingestors.fuzz_finding_ingestor import FuzzFindingIngestor
from api.infrastructure.ingestors.javascript_reference_finding_ingestor import (
    JavaScriptReferenceFindingIngestor,
)
from api.infrastructure.ingestors.naabu_ingestor import NaabuResultIngestor
from api.infrastructure.ingestors.service_finding_ingestor import ServiceFindingIngestor
from api.infrastructure.ingestors.url_finding_ingestor import UrlFindingIngestor
from api.infrastructure.parsers.line_process_event_parsers import NaabuStdoutParser
from api.infrastructure.schemas.models.process_event import ProcessEvent


class FakeIPAddresses:
    def __init__(self) -> None:
        self.rows: dict[tuple[object, str], SimpleNamespace] = {}
        self.ensure_calls: list[dict[str, object]] = []

    async def ensure(self, *, program_id, address, in_scope=True):
        self.ensure_calls.append(
            {"program_id": program_id, "address": address, "in_scope": in_scope}
        )
        return self.rows.setdefault(
            (program_id, address),
            SimpleNamespace(id=uuid4(), address=address),
        )


class FakeServices:
    def __init__(self) -> None:
        self.ensure_calls: list[dict[str, object]] = []

    async def ensure(self, *, ip_id, scheme, port, technologies):
        self.ensure_calls.append(
            {
                "ip_id": ip_id,
                "scheme": scheme,
                "port": port,
                "technologies": technologies,
            }
        )
        return SimpleNamespace(id=uuid4(), ip_id=ip_id, scheme=scheme, port=port)


class FakeUnitOfWork:
    def __init__(self) -> None:
        self.ip_addresses = FakeIPAddresses()
        self.services = FakeServices()
        self.commits = 0
        self.rollbacks = 0
        self.savepoints: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def create_savepoint(self, name: str):
        self.savepoints.append(name)

    async def release_savepoint(self, name: str):
        return None

    async def rollback_to_savepoint(self, name: str):
        raise AssertionError("unexpected rollback")

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


class SettingsStub:
    SERVICE_FINDING_BATCH_MIN = 2
    SERVICE_FINDING_BATCH_MAX = 2
    SERVICE_FINDING_BATCH_TIMEOUT = 100.0
    NAABU_INGESTOR_BATCH_SIZE = 100


async def _events(*events: ProcessEvent):
    for event in events:
        yield event


@pytest.mark.asyncio
async def test_naabu_parser_emits_service_findings() -> None:
    parser = NaabuStdoutParser()

    records = [
        event
        async for event in parser.parse_stream(
            _events(
                ProcessEvent(
                    type="stdout",
                    payload='{"ip":"203.0.113.10","port":443,"protocol":"tcp"}',
                )
            )
        )
    ]

    assert records == [
        ProcessEvent(
            type="canonical_record",
            payload=ServiceFinding(
                ip="203.0.113.10",
                port=443,
                protocol="tcp",
                source_tool="naabu",
                scheme="https",
                raw={"ip": "203.0.113.10", "port": 443, "protocol": "tcp"},
            ),
        )
    ]


@pytest.mark.asyncio
async def test_service_finding_processor_batches_only_service_records() -> None:
    processor = ServiceFindingBatchProcessor(SettingsStub())

    batches = [
        batch
        async for batch in processor.batch_stream(
            _events(
                ProcessEvent(type="canonical_record", payload="noise"),
                ProcessEvent(
                    type="canonical_record",
                    payload=ServiceFinding("203.0.113.10", 80, "naabu"),
                ),
                ProcessEvent(
                    type="canonical_record",
                    payload=ServiceFinding("203.0.113.11", 443, "naabu"),
                ),
            )
        )
    ]

    assert batches == [[
        ServiceFinding("203.0.113.10", 80, "naabu"),
        ServiceFinding("203.0.113.11", 443, "naabu"),
    ]]


def test_service_finding_processor_uses_service_batch_settings() -> None:
    processor = ServiceFindingBatchProcessor(SettingsStub())

    assert processor._get_batch_config(SettingsStub()) == {
        "min": 2,
        "max": 2,
        "timeout": 100.0,
    }


@pytest.mark.asyncio
async def test_canonical_router_persists_service_findings_by_fact_type() -> None:
    program_id = uuid4()
    uow = FakeUnitOfWork()
    router = CanonicalIngestorRouter(
        host_findings=object(),  # type: ignore[arg-type]
        url_findings=UrlFindingIngestor(),
        javascript_references=JavaScriptReferenceFindingIngestor(),
        fuzz_findings=FuzzFindingIngestor(),
        service_findings=ServiceFindingIngestor(uow=uow),
    )

    result = await router.ingest(
        program_id,
        [
            ServiceFinding("203.0.113.10", 443, "naabu", protocol="tcp"),
            ServiceFinding(
                "203.0.113.10",
                8443,
                "smap",
                service_name="https-alt",
            ),
        ],
    )

    assert result.ips == ["203.0.113.10"]
    assert [call["address"] for call in uow.ip_addresses.ensure_calls] == [
        "203.0.113.10",
        "203.0.113.10",
    ]
    assert [call["port"] for call in uow.services.ensure_calls] == [443, 8443]
    assert uow.services.ensure_calls[0]["scheme"] == "https"
    assert uow.services.ensure_calls[1]["technologies"]["service"] == "https-alt"
    assert uow.commits == 1


@pytest.mark.asyncio
async def test_service_finding_ingestor_rejects_legacy_payload_shape() -> None:
    ingestor = ServiceFindingIngestor(uow=FakeUnitOfWork())

    with pytest.raises(TypeError, match="expects ServiceFinding"):
        await ingestor.process_record(
            FakeUnitOfWork(),
            uuid4(),
            {"ip": "203.0.113.10", "port": 443},  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_naabu_ingestor_keeps_legacy_payload_compatibility() -> None:
    program_id = uuid4()
    uow = FakeUnitOfWork()
    ingestor = NaabuResultIngestor(uow=uow, settings=SettingsStub())  # type: ignore[arg-type]

    result = await ingestor.ingest(
        program_id,
        [{"ip": "203.0.113.20", "port": 80, "protocol": "tcp"}],
    )

    assert result.ips == ["203.0.113.20"]
    assert uow.services.ensure_calls[0]["scheme"] == "http"
