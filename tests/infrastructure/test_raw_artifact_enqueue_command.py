from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4


def _raw_artifact_row(**overrides):
    program_id = overrides.pop("program_id", uuid4())
    run_id = overrides.pop("run_id", uuid4())
    artifact_id = overrides.pop("id", uuid4())
    row = {
        "id": artifact_id,
        "program_id": program_id,
        "job_id": uuid4(),
        "run_id": run_id,
        "node_id": "httpx",
        "event_name": "httpx.completed",
        "artifact_type": "raw_tool_output",
        "storage_uri": f"raw://{artifact_id}.ndjson",
        "sha256": "a" * 64,
        "size_bytes": 1234,
        "artifact_metadata": {"targets": ["api.example.com"], "runner": "HTTPXRunner"},
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "projection_event_id": uuid4(),
        "projection_event_attempts": 1,
    }
    row.update(overrides)
    return row


def _symbols():
    import sys

    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.producers.raw_artifacts import (
        RawArtifactGraphFactEnqueuer,
        RawArtifactGraphFactProducer,
        raw_artifact_dedupe_key,
    )

    return RawArtifactGraphFactEnqueuer, RawArtifactGraphFactProducer, raw_artifact_dedupe_key


class RecordingCursor:
    def __init__(self, rows):
        self.rows = rows
        self.calls: list[tuple[str, dict[str, object]]] = []

    def execute(self, query: str, parameters: dict[str, object] | None = None):
        self.calls.append((query, parameters or {}))

    def fetchall(self):
        return self.rows


class RecordingConnection:
    def __init__(self, rows):
        self.cursor_obj = RecordingCursor(rows)
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class RecordingBatchStore:
    def __init__(self) -> None:
        self.calls: list[tuple[object, str | None]] = []

    def enqueue(self, batch, *, dedupe_key: str | None = None):
        self.calls.append((batch, dedupe_key))
        return uuid4()


def test_raw_artifact_dedupe_key_is_stable_per_artifact_and_parser_version() -> None:
    _, _, raw_artifact_dedupe_key = _symbols()

    artifact_id = uuid4()

    assert raw_artifact_dedupe_key(artifact_id, "raw-artifact-metadata.v1") == (
        f"raw-artifact-metadata:{artifact_id}:raw-artifact-metadata.v1"
    )


def test_raw_artifact_enqueuer_reads_rows_and_enqueues_idempotent_batches() -> None:
    RawArtifactGraphFactEnqueuer, RawArtifactGraphFactProducer, raw_artifact_dedupe_key = _symbols()

    row = _raw_artifact_row()
    connection = RecordingConnection([row])
    store = RecordingBatchStore()
    producer = RawArtifactGraphFactProducer(parser_version="raw-artifact-metadata.v1")
    enqueuer = RawArtifactGraphFactEnqueuer(
        connection=connection,
        store=store,
        producer=producer,
    )

    result = enqueuer.enqueue_pending(limit=25)

    assert result.scanned == 1
    assert result.enqueued == 1
    assert result.skipped == 0
    query, parameters = connection.cursor_obj.calls[0]
    assert "FROM graph_projection_events" in query
    assert "raw_artifact_created" in query
    assert "FOR UPDATE SKIP LOCKED" in query
    assert "JOIN raw_artifacts" in query
    assert "run_id IS NOT NULL" in query
    assert "ORDER BY raw_artifacts.created_at ASC, raw_artifacts.id ASC" in query
    assert parameters["limit"] == 25
    batch, dedupe_key = store.calls[0]
    assert batch.program_id == row["program_id"]
    assert dedupe_key == raw_artifact_dedupe_key(row["id"], "raw-artifact-metadata.v1")


def test_raw_artifact_enqueue_command_is_exposed_without_apply_loop() -> None:
    source = Path("services/graph-projector/graph_projector/__main__.py").read_text(encoding="utf-8")

    assert 'subparsers.add_parser("enqueue-raw-artifacts"' in source
    assert "RawArtifactGraphFactEnqueuer" in source
    assert "while True" not in source
