from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pytest

from api.application.services.raw_artifact_parser import RawArtifactParserService
from api.infrastructure.artifacts.raw_output_store import FileRawOutputStore
from api.infrastructure.parsers.raw_artifact_parser import ProcessEventArtifactParser
from api.application.process_event_contracts import ProcessEvent


async def _stream(*events: ProcessEvent):
    for event in events:
        yield event


async def _capture(
    store: FileRawOutputStore,
    *,
    artifact_id,
    target: str,
) -> tuple[list[ProcessEvent], dict]:
    recorded: list[dict] = []
    event = ProcessEvent(type="stdout", payload='{"url":"https://example.com"}')

    async def record(metadata: dict) -> None:
        recorded.append(metadata)

    captured = [
        item
        async for item in store.capture_stream(
            _stream(event),
            program_id=uuid4(),
            node_id="http-probe",
            event_name="http.discovered",
            targets=[target],
            artifact_id=artifact_id,
            metadata={"runner": "HTTPXRunner"},
            recorder=record,
        )
    ]

    return captured, recorded[0]


@pytest.mark.asyncio
async def test_identical_event_blobs_are_stored_once_by_sha256(tmp_path: Path) -> None:
    store = FileRawOutputStore(tmp_path)

    first_events, first_metadata = await _capture(
        store,
        artifact_id=uuid4(),
        target="first.example.com",
    )
    second_events, second_metadata = await _capture(
        store,
        artifact_id=uuid4(),
        target="second.example.com",
    )

    assert first_events == second_events
    assert first_metadata["id"] != second_metadata["id"]
    assert first_metadata["artifact_metadata"] != second_metadata["artifact_metadata"]
    assert first_metadata["storage_uri"] == second_metadata["storage_uri"]
    assert first_metadata["sha256"] == second_metadata["sha256"]
    assert first_metadata["content_encoding"] == "identity"
    assert first_metadata["retention_class"] == "program_lifetime"
    assert first_metadata["storage_size_bytes"] == first_metadata["size_bytes"]

    blob_path = Path(first_metadata["storage_uri"])
    assert blob_path == (
        tmp_path
        / "blobs"
        / "sha256"
        / first_metadata["sha256"][:2]
        / first_metadata["sha256"][2:4]
        / f"{first_metadata['sha256']}.ndjson"
    )
    assert hashlib.sha256(blob_path.read_bytes()).hexdigest() == first_metadata["sha256"]
    assert list((tmp_path / "blobs").rglob("*.ndjson")) == [blob_path]


@pytest.mark.asyncio
async def test_parser_rehydrates_artifact_context_from_metadata_row(tmp_path: Path) -> None:
    artifact_id = uuid4()
    program_id = uuid4()
    recorded: list[dict] = []
    store = FileRawOutputStore(tmp_path)

    async def record(metadata: dict) -> None:
        recorded.append(metadata)

    async for _ in store.capture_stream(
        _stream(ProcessEvent(type="stdout", payload='{"host":"example.com"}')),
        program_id=program_id,
        node_id="subdomain-enumeration",
        event_name="subdomain.discovered",
        targets=["example.com"],
        artifact_id=artifact_id,
        metadata={"runner": "SubfinderRunner"},
        recorder=record,
    ):
        pass

    parsed = RawArtifactParserService(ProcessEventArtifactParser()).parse_metadata_row(recorded[0])
    blob_text = Path(recorded[0]["storage_uri"]).read_text(encoding="utf-8")

    assert '"type": "metadata"' not in blob_text
    assert parsed.metadata["artifact_id"] == str(artifact_id)
    assert parsed.metadata["program_id"] == str(program_id)
    assert parsed.metadata["node_id"] == "subdomain-enumeration"
    assert parsed.metadata["event_name"] == "subdomain.discovered"
    assert parsed.metadata["runner"] == "SubfinderRunner"
    assert parsed.records[0].artifact_id == artifact_id
    assert parsed.records[0].tool == "SubfinderRunner"


def test_parser_keeps_legacy_embedded_metadata_compatible(tmp_path: Path) -> None:
    artifact_id = uuid4()
    artifact_path = tmp_path / "legacy.ndjson"
    artifact_path.write_text(
        "\n".join(
            (
                json.dumps(
                    {
                        "type": "metadata",
                        "payload": {
                            "artifact_id": str(artifact_id),
                            "runner": "LegacyRunner",
                            "node_id": "legacy-node",
                            "event_name": "legacy.event",
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "stdout",
                        "payload": '{"host":"legacy.example.com"}',
                    }
                ),
            )
        )
        + "\n",
        encoding="utf-8",
    )

    parsed = ProcessEventArtifactParser().parse_path(artifact_path)

    assert parsed.records[0].artifact_id == artifact_id
    assert parsed.records[0].tool == "LegacyRunner"


@pytest.mark.asyncio
async def test_failed_metadata_record_keeps_unique_reconcile_marker(tmp_path: Path) -> None:
    artifact_id = uuid4()
    store = FileRawOutputStore(tmp_path)

    async def fail_record(_: dict) -> None:
        raise RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="database unavailable"):
        async for _ in store.capture_stream(
            _stream(ProcessEvent(type="stdout", payload="example.com")),
            program_id=uuid4(),
            node_id="subdomain-enumeration",
            event_name="subdomain.discovered",
            targets=["example.com"],
            artifact_id=artifact_id,
            recorder=fail_record,
        ):
            pass

    markers = list((tmp_path / "blobs").rglob("*.ndjson.reconcile.json"))
    assert len(markers) == 1
    assert str(artifact_id) in markers[0].name


@pytest.mark.asyncio
async def test_artifact_is_recorded_before_first_event_is_replayed(
    tmp_path: Path,
) -> None:
    recorded: list[dict] = []
    store = FileRawOutputStore(tmp_path)

    async def record(metadata: dict) -> None:
        assert Path(metadata["storage_uri"]).exists()
        recorded.append(metadata)

    captured = store.capture_stream(
        _stream(
            ProcessEvent(type="stdout", payload="first"),
            ProcessEvent(type="stdout", payload="second"),
        ),
        program_id=uuid4(),
        node_id="subdomain-enumeration",
        event_name="subdomain.discovered",
        targets=["example.com"],
        recorder=record,
    )

    first_event = await anext(captured)

    assert first_event.payload == "first"
    assert len(recorded) == 1


@pytest.mark.asyncio
async def test_large_blob_is_gzip_compressed_and_replayed_transparently(
    tmp_path: Path,
) -> None:
    recorded: list[dict] = []
    events = (
        ProcessEvent(type="stdout", payload="a" * 128),
        ProcessEvent(type="stderr", payload="b" * 128),
    )
    store = FileRawOutputStore(tmp_path, compression_threshold_bytes=1)

    async def record(metadata: dict) -> None:
        recorded.append(metadata)

    replayed = [
        event
        async for event in store.capture_stream(
            _stream(*events),
            program_id=uuid4(),
            node_id="large-output",
            event_name="large.completed",
            targets=["example.com"],
            retention_class="short_lived",
            recorder=record,
        )
    ]

    metadata = recorded[0]
    blob_path = Path(metadata["storage_uri"])
    uncompressed = gzip.decompress(blob_path.read_bytes())

    assert replayed == list(events)
    assert blob_path.suffixes[-2:] == [".ndjson", ".gz"]
    assert metadata["content_encoding"] == "gzip"
    assert metadata["retention_class"] == "short_lived"
    assert metadata["size_bytes"] == len(uncompressed)
    assert metadata["storage_size_bytes"] == blob_path.stat().st_size
    assert hashlib.sha256(uncompressed).hexdigest() == metadata["sha256"]


@pytest.mark.asyncio
async def test_parser_service_reads_compressed_artifact(tmp_path: Path) -> None:
    recorded: list[dict] = []
    store = FileRawOutputStore(tmp_path, compression_threshold_bytes=1)

    async def record(metadata: dict) -> None:
        recorded.append(metadata)

    async for _ in store.capture_stream(
        _stream(ProcessEvent(type="stdout", payload='{"host":"compressed.example"}')),
        program_id=uuid4(),
        node_id="subdomain-enumeration",
        event_name="subdomain.discovered",
        targets=["example.com"],
        metadata={"runner": "SubfinderRunner"},
        recorder=record,
    ):
        pass

    parsed = RawArtifactParserService(ProcessEventArtifactParser()).parse_metadata_row(recorded[0])

    assert parsed.records[0].payload == {"host": "compressed.example"}


@pytest.mark.asyncio
async def test_existing_blob_is_reused_when_compression_threshold_changes(
    tmp_path: Path,
) -> None:
    event = ProcessEvent(type="stdout", payload="same-content" * 32)
    metadata_rows: list[dict] = []

    async def record(metadata: dict) -> None:
        metadata_rows.append(metadata)

    async for _ in FileRawOutputStore(
        tmp_path,
        compression_threshold_bytes=10_000,
    ).capture_stream(
        _stream(event),
        program_id=uuid4(),
        node_id="probe",
        event_name="probe.completed",
        targets=["example.com"],
        recorder=record,
    ):
        pass

    async for _ in FileRawOutputStore(
        tmp_path,
        compression_threshold_bytes=1,
    ).capture_stream(
        _stream(event),
        program_id=uuid4(),
        node_id="probe",
        event_name="probe.completed",
        targets=["example.com"],
        recorder=record,
    ):
        pass

    assert metadata_rows[0]["storage_uri"] == metadata_rows[1]["storage_uri"]
    assert len(list((tmp_path / "blobs").rglob("*.ndjson*"))) == 1


@pytest.mark.asyncio
async def test_capture_persists_bounded_sanitized_preview_with_safe_flags(
    tmp_path: Path,
) -> None:
    recorded: list[dict] = []
    store = FileRawOutputStore(tmp_path, preview_limit_bytes=256)

    async def record(metadata: dict) -> None:
        recorded.append(metadata)

    async for _ in store.capture_stream(
        _stream(
            ProcessEvent(
                type="stdout",
                payload=(
                    "Authorization: Bearer secret-token\n"
                    "Cookie: session=secret-cookie\n"
                    + ("x" * 1024)
                ),
            )
        ),
        program_id=uuid4(),
        node_id="http-probe",
        event_name="http.completed",
        targets=["example.com"],
        recorder=record,
    ):
        pass

    metadata = recorded[0]

    assert metadata["raw_safe_for_llm"] is False
    assert metadata["sanitized_safe_for_llm"] is True
    assert metadata["sanitizer_version"]
    assert len(metadata["preview"].encode("utf-8")) <= 256
    assert "secret-token" in metadata["preview"]
    assert "secret-token" not in metadata["sanitized_preview"]
    assert "secret-cookie" not in metadata["sanitized_preview"]


@pytest.mark.asyncio
async def test_capture_records_explicit_parser_scope_target_and_parent_lineage(
    tmp_path: Path,
) -> None:
    recorded: list[dict] = []
    scope_decision_id = uuid4()
    parent_artifact_id = uuid4()
    store = FileRawOutputStore(tmp_path)

    async def record(metadata: dict) -> None:
        recorded.append(metadata)

    async for _ in store.capture_stream(
        _stream(ProcessEvent(type="stdout", payload="example.com")),
        program_id=uuid4(),
        node_id="subdomain-enumeration",
        event_name="subdomain.discovered",
        targets=["example.com", "api.example.com"],
        parser_name="SubfinderStdoutParser",
        parser_version="2",
        scope_decision_id=scope_decision_id,
        parent_artifact_id=parent_artifact_id,
        recorder=record,
    ):
        pass

    metadata = recorded[0]

    assert metadata["parser_name"] == "SubfinderStdoutParser"
    assert metadata["parser_version"] == "2"
    assert metadata["scope_decision_id"] == scope_decision_id
    assert metadata["source_targets"] == ["example.com", "api.example.com"]
    assert metadata["parent_artifact_id"] == parent_artifact_id
