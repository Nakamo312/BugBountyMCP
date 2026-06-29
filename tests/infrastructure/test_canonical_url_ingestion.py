from __future__ import annotations

from uuid import uuid4

import pytest

from api.application.pipeline.canonical_processor import UrlEvidenceBatchProcessor
from api.application.pipeline.records import (
    FuzzFinding,
    JavaScriptReferenceFinding,
    UrlFinding,
)
from api.infrastructure.ingestors.canonical_router import CanonicalIngestorRouter
from api.infrastructure.ingestors.ingest_result import IngestResult
from api.infrastructure.ingestors.fuzz_finding_ingestor import FuzzFindingIngestor
from api.infrastructure.ingestors.javascript_reference_finding_ingestor import (
    JavaScriptReferenceFindingIngestor,
)
from api.infrastructure.ingestors.url_finding_ingestor import UrlFindingIngestor
from api.infrastructure.parsers.line_process_event_parsers import (
    FFUFStdoutParser,
    KatanaStdoutParser,
    LinkFinderStdoutParser,
    WaymoreStdoutParser,
)
from api.infrastructure.schemas.models.process_event import ProcessEvent


class SettingsStub:
    URL_FINDING_BATCH_MIN = 2
    URL_FINDING_BATCH_MAX = 3
    URL_FINDING_BATCH_TIMEOUT = 100.0


class FakeHostFindingIngestor:
    async def ingest(self, program_id, findings, context=None):
        return IngestResult(raw_domains=[finding.host for finding in findings])


async def _events(*events: ProcessEvent):
    for event in events:
        yield event


@pytest.mark.asyncio
async def test_waymore_parser_emits_url_finding_records() -> None:
    parser = WaymoreStdoutParser()

    records = [
        event
        async for event in parser.parse_stream(
            _events(
                ProcessEvent(type="stdout", payload="https://example.com/a"),
                ProcessEvent(type="stdout", payload="not-a-url"),
            )
        )
    ]

    assert records == [
        ProcessEvent(
            type="canonical_record",
            payload=UrlFinding(
                url="https://example.com/a",
                source_tool="waymore",
                raw="https://example.com/a",
            ),
        )
    ]


@pytest.mark.asyncio
async def test_katana_parser_emits_url_finding_without_endpoint_materialization() -> None:
    parser = KatanaStdoutParser()

    records = [
        event
        async for event in parser.parse_stream(
            _events(
                ProcessEvent(
                    type="stdout",
                    payload=(
                        '{"request":{"endpoint":"https://app.example.com/app.js",'
                        '"method":"GET"},"response":{"status_code":200,'
                        '"headers":{"content-type":"application/javascript"}}}'
                    ),
                )
            )
        )
    ]

    assert records == [
        ProcessEvent(
            type="canonical_record",
            payload=UrlFinding(
                url="https://app.example.com/app.js",
                source_tool="katana",
                source_target="app.example.com",
                metadata={
                    "method": "GET",
                    "status_code": 200,
                    "content_type": "application/javascript",
                    "asset_type": "javascript",
                },
                raw={
                    "request": {
                        "endpoint": "https://app.example.com/app.js",
                        "method": "GET",
                    },
                    "response": {
                        "status_code": 200,
                        "headers": {"content-type": "application/javascript"},
                    },
                },
            ),
        )
    ]


@pytest.mark.asyncio
async def test_katana_parser_skips_non_absolute_urls() -> None:
    parser = KatanaStdoutParser()

    records = [
        event
        async for event in parser.parse_stream(
            _events(
                ProcessEvent(
                    type="stdout",
                    payload='{"request":{"endpoint":"/api/users"}}',
                ),
                ProcessEvent(
                    type="stdout",
                    payload='{"request":{"endpoint":"api/users"}}',
                ),
                ProcessEvent(
                    type="stdout",
                    payload='{"request":{"endpoint":"//cdn.example.com/app.js"}}',
                ),
                ProcessEvent(
                    type="stdout",
                    payload='{"request":{"endpoint":"ftp://example.com/app.js"}}',
                ),
                ProcessEvent(
                    type="stdout",
                    payload='{"request":{"endpoint":"https://example.com/app.js"}}',
                ),
            )
        )
    ]

    assert records == [
        ProcessEvent(
            type="canonical_record",
            payload=UrlFinding(
                url="https://example.com/app.js",
                source_tool="katana",
                source_target="example.com",
                metadata={"method": "GET", "asset_type": "javascript"},
                raw={"request": {"endpoint": "https://example.com/app.js"}},
            ),
        )
    ]


@pytest.mark.asyncio
async def test_ffuf_parser_emits_url_and_fuzz_evidence_without_materialization() -> None:
    parser = FFUFStdoutParser()

    records = [
        event
        async for event in parser.parse_stream(
            _events(
                ProcessEvent(
                    type="stdout",
                    payload=(
                        '{"url":"https://example.com/admin","status":200,'
                        '"length":1234,"words":42,"lines":9,'
                        '"redirectlocation":"https://example.com/login"}'
                    ),
                )
            )
        )
    ]

    assert records == [
        ProcessEvent(
            type="canonical_record",
            payload=UrlFinding(
                url="https://example.com/admin",
                source_tool="ffuf",
                source_target="example.com",
                metadata={"evidence_type": "fuzz_candidate"},
                raw={
                    "url": "https://example.com/admin",
                    "status": 200,
                    "length": 1234,
                    "words": 42,
                    "lines": 9,
                    "redirectlocation": "https://example.com/login",
                },
            ),
        ),
        ProcessEvent(
            type="canonical_record",
            payload=FuzzFinding(
                url="https://example.com/admin",
                source_tool="ffuf",
                source_target="example.com",
                status_code=200,
                length=1234,
                words=42,
                lines=9,
                redirect_location="https://example.com/login",
                raw={
                    "url": "https://example.com/admin",
                    "status": 200,
                    "length": 1234,
                    "words": 42,
                    "lines": 9,
                    "redirectlocation": "https://example.com/login",
                },
            ),
        ),
    ]


@pytest.mark.asyncio
async def test_ffuf_parser_skips_non_absolute_urls() -> None:
    parser = FFUFStdoutParser()

    records = [
        event
        async for event in parser.parse_stream(
            _events(
                ProcessEvent(type="stdout", payload='{"url":"/admin","status":200}'),
                ProcessEvent(type="stdout", payload='{"url":"admin","status":200}'),
                ProcessEvent(type="stdout", payload='{"url":"//example.com/admin","status":200}'),
                ProcessEvent(type="stdout", payload='{"url":"ftp://example.com/admin","status":200}'),
                ProcessEvent(type="stdout", payload='{"url":"https://example.com/admin","status":200}'),
            )
        )
    ]

    assert [event.payload for event in records] == [
        UrlFinding(
            url="https://example.com/admin",
            source_tool="ffuf",
            source_target="example.com",
            metadata={"evidence_type": "fuzz_candidate"},
            raw={"url": "https://example.com/admin", "status": 200},
        ),
        FuzzFinding(
            url="https://example.com/admin",
            source_tool="ffuf",
            source_target="example.com",
            status_code=200,
            raw={"url": "https://example.com/admin", "status": 200},
        ),
    ]


@pytest.mark.asyncio
async def test_linkfinder_parser_emits_url_evidence_and_js_reference() -> None:
    parser = LinkFinderStdoutParser()

    records = [
        event
        async for event in parser.parse_stream(
            _events(
                ProcessEvent(
                    type="target",
                    payload={
                        "target": "https://app.example.com/static/app.js",
                        "host": "app.example.com",
                    },
                ),
                ProcessEvent(type="stdout", payload="/api/users"),
            )
        )
    ]

    assert records == [
        ProcessEvent(
            type="canonical_record",
            payload=JavaScriptReferenceFinding(
                source_url="https://app.example.com/static/app.js",
                referenced_url="https://app.example.com/api/users",
                source_tool="linkfinder",
                source_target="app.example.com",
            ),
        ),
        ProcessEvent(
            type="canonical_record",
            payload=UrlFinding(
                url="https://app.example.com/api/users",
                source_tool="linkfinder",
                source_target="app.example.com",
                discovered_from="https://app.example.com/static/app.js",
            ),
        ),
    ]


@pytest.mark.asyncio
async def test_url_evidence_processor_keeps_distinct_url_observations() -> None:
    processor = UrlEvidenceBatchProcessor(SettingsStub())
    plain = UrlFinding("https://example.com/app.js", "waymore")
    js = UrlFinding(
        "https://example.com/app.js",
        "katana",
        metadata={"asset_type": "javascript"},
    )
    fuzz = FuzzFinding("https://example.com/app.js", "ffuf", status_code=200)
    reference = JavaScriptReferenceFinding(
        source_url="https://example.com/app.js",
        referenced_url="https://example.com/app.js",
        source_tool="linkfinder",
    )

    batches = [
        batch
        async for batch in processor.batch_stream(
            _events(
                ProcessEvent(type="canonical_record", payload=plain),
                ProcessEvent(type="canonical_record", payload=js),
                ProcessEvent(type="canonical_record", payload=fuzz),
                ProcessEvent(type="canonical_record", payload=fuzz),
                ProcessEvent(type="canonical_record", payload=reference),
                ProcessEvent(type="canonical_record", payload=reference),
            )
        )
    ]

    assert batches == [[plain, js, fuzz], [reference]]


@pytest.mark.asyncio
async def test_url_finding_ingestor_returns_urls_without_endpoint_materialization() -> None:
    ingestor = UrlFindingIngestor()
    program_id = uuid4()

    result = await ingestor.ingest(
        program_id,
        [
            UrlFinding("https://example.com/a", "waymore"),
            UrlFinding("https://example.com/a", "linkfinder"),
            UrlFinding("https://example.com/b", "linkfinder"),
        ],
    )

    assert result.urls == ["https://example.com/a", "https://example.com/b"]
    assert result.raw_domains == []


@pytest.mark.asyncio
async def test_url_finding_ingestor_returns_js_files_from_javascript_url_evidence() -> None:
    ingestor = UrlFindingIngestor()

    result = await ingestor.ingest(
        uuid4(),
        [
            UrlFinding("https://example.com/app.js", "waymore"),
            UrlFinding(
                "https://example.com/app.js",
                "katana",
                metadata={"asset_type": "javascript"},
            ),
            UrlFinding("https://example.com/api", "katana"),
        ],
    )

    assert result.urls == ["https://example.com/app.js", "https://example.com/api"]
    assert result.js_files == ["https://example.com/app.js"]


@pytest.mark.asyncio
async def test_url_evidence_processor_to_router_preserves_javascript_observation() -> None:
    processor = UrlEvidenceBatchProcessor(SettingsStub())
    router = CanonicalIngestorRouter(
        host_findings=FakeHostFindingIngestor(),  # type: ignore[arg-type]
        url_findings=UrlFindingIngestor(),
        javascript_references=JavaScriptReferenceFindingIngestor(),
        fuzz_findings=FuzzFindingIngestor(),
        service_findings=object(),  # type: ignore[arg-type]
    )
    plain = UrlFinding("https://example.com/app.js", "waymore")
    js = UrlFinding(
        "https://example.com/app.js",
        "katana",
        metadata={"asset_type": "javascript"},
    )

    batches = [
        batch
        async for batch in processor.batch_stream(
            _events(
                ProcessEvent(type="canonical_record", payload=plain),
                ProcessEvent(type="canonical_record", payload=js),
            )
        )
    ]

    result = IngestResult()
    for batch in batches:
        result = result.merge(await router.ingest(uuid4(), batch))

    assert result.urls == ["https://example.com/app.js"]
    assert result.js_files == ["https://example.com/app.js"]


@pytest.mark.asyncio
async def test_javascript_reference_finding_ingestor_does_not_materialize_endpoints() -> None:
    ingestor = JavaScriptReferenceFindingIngestor()

    result = await ingestor.ingest(
        uuid4(),
        [
            JavaScriptReferenceFinding(
                source_url="https://example.com/app.js",
                referenced_url="https://example.com/api",
                source_tool="linkfinder",
            )
        ],
    )

    assert result == IngestResult()


@pytest.mark.asyncio
async def test_fuzz_finding_ingestor_does_not_materialize_endpoints() -> None:
    ingestor = FuzzFindingIngestor()

    result = await ingestor.ingest(
        uuid4(),
        [
            FuzzFinding(
                url="https://example.com/admin",
                source_tool="ffuf",
                status_code=200,
            )
        ],
    )

    assert result == IngestResult()


@pytest.mark.asyncio
async def test_canonical_router_routes_url_and_js_reference_evidence() -> None:
    router = CanonicalIngestorRouter(
        host_findings=FakeHostFindingIngestor(),  # type: ignore[arg-type]
        url_findings=UrlFindingIngestor(),
        javascript_references=JavaScriptReferenceFindingIngestor(),
        fuzz_findings=FuzzFindingIngestor(),
        service_findings=object(),  # type: ignore[arg-type]
    )

    result = await router.ingest(
        uuid4(),
        [
            JavaScriptReferenceFinding(
                source_url="https://example.com/app.js",
                referenced_url="https://example.com/api",
                source_tool="linkfinder",
            ),
            UrlFinding("https://example.com/api", "linkfinder"),
            FuzzFinding("https://example.com/api", "ffuf", status_code=200),
        ],
    )

    assert result.urls == ["https://example.com/api"]
