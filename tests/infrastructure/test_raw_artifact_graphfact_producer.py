from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from tests.infrastructure.graph_projector_cli_test_helpers import graph_projector_cli_source


def _symbols():
    import sys

    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.batch_store import GraphFactBatchStore
    from graph_projector.producers.raw_artifacts import RawArtifactGraphFactProducer

    return RawArtifactGraphFactProducer, GraphFactBatchStore


class RecordingCursor:
    def __init__(self, row):
        self.row = row
        self.calls: list[tuple[str, dict[str, object]]] = []

    def execute(self, query: str, parameters: dict[str, object] | None = None):
        self.calls.append((query, parameters or {}))

    def fetchone(self):
        return self.row


class RecordingConnection:
    def __init__(self, row):
        self.cursor_obj = RecordingCursor(row)
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


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


def test_raw_artifact_producer_builds_l0_graphfact_batch_from_artifact_metadata() -> None:
    RawArtifactGraphFactProducer, _ = _symbols()

    row = _raw_artifact_row()
    batch = RawArtifactGraphFactProducer(parser_version="raw-artifact-metadata.v1").produce(row)

    assert batch is not None
    assert batch.program_id == row["program_id"]
    assert batch.produced_by == "raw-artifact-metadata"
    assert batch.parser_version == "raw-artifact-metadata.v1"

    node_facts = {(fact.kind, fact.key) for fact in batch.facts if hasattr(fact, "kind")}
    assert ("Program", str(row["program_id"])) in node_facts
    assert ("Tool", "httpx") in node_facts
    assert ("ToolRun", str(row["run_id"])) in node_facts
    assert ("Artifact", str(row["id"])) in node_facts

    edge_facts = {
        (fact.src_kind, fact.src_key, fact.edge_kind, fact.dst_kind, fact.dst_key)
        for fact in batch.facts
        if hasattr(fact, "edge_kind")
    }
    assert ("Program", str(row["program_id"]), "HAS_TOOL_RUN", "ToolRun", str(row["run_id"])) in edge_facts
    assert ("ToolRun", str(row["run_id"]), "USED_TOOL", "Tool", "httpx") in edge_facts
    assert ("ToolRun", str(row["run_id"]), "PRODUCED_ARTIFACT", "Artifact", str(row["id"])) in edge_facts

    for fact in batch.facts:
        assert fact.source_artifact_id == row["id"]
        assert fact.tool_run_id == row["run_id"]
        assert fact.confidence == 1.0


def test_raw_artifact_producer_skips_artifacts_without_run_lineage() -> None:
    RawArtifactGraphFactProducer, _ = _symbols()

    batch = RawArtifactGraphFactProducer().produce(_raw_artifact_row(run_id=None))

    assert batch is None


def test_batch_store_enqueue_persists_serialized_graphfact_batch() -> None:
    RawArtifactGraphFactProducer, GraphFactBatchStore = _symbols()

    batch_id = uuid4()
    row = _raw_artifact_row()
    batch = RawArtifactGraphFactProducer().produce(row)
    connection = RecordingConnection({"id": batch_id})
    store = GraphFactBatchStore(connection)

    returned_id = store.enqueue(batch)

    assert returned_id == batch_id
    assert connection.commits == 1
    assert connection.rollbacks == 0
    query, parameters = connection.cursor_obj.calls[0]
    assert "INSERT INTO graph_fact_batches" in query
    assert "RETURNING id" in query
    assert parameters["program_id"] == str(row["program_id"])
    assert parameters["produced_by"] == "raw-artifact-metadata"
    assert parameters["parser_version"] == "raw-artifact-metadata.v1"
    assert parameters["fact_count"] == len(batch.facts)
    assert parameters["facts_json"]["facts"]

class SequenceRawArtifactEnqueuer:
    def __init__(self, results):
        self.results = list(results)
        self.calls: list[tuple[int, object]] = []

    def enqueue_pending(self, *, limit: int = 100, program_id=None):
        self.calls.append((limit, program_id))
        if not self.results:
            return RawArtifactEnqueueResult(scanned=0, enqueued=0, skipped=0)
        return self.results.pop(0)


def test_raw_artifact_fetch_claims_durable_projection_events_instead_of_scanning_artifacts() -> None:
    source = Path("services/graph-projector/graph_projector/producers/raw_artifact_claims.py").read_text(encoding="utf-8")

    assert "FROM graph_projection_events" in source
    assert "raw_artifact_created" in source
    assert "FOR UPDATE SKIP LOCKED" in source
    assert "JOIN raw_artifacts" in source
    assert "NOT EXISTS" not in source


def test_raw_artifact_enqueue_loop_stops_after_idle_threshold_and_sleeps() -> None:
    import sys

    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.producers.raw_artifacts import RawArtifactEnqueueLoopResult, RawArtifactEnqueueResult

    active = RawArtifactEnqueueResult(scanned=2, enqueued=2, skipped=0)
    empty = RawArtifactEnqueueResult(scanned=0, enqueued=0, skipped=0)
    enqueuer = SequenceRawArtifactEnqueuer([active, empty, empty])
    slept: list[float] = []

    result = RawArtifactEnqueueLoopResult.run(
        enqueuer,
        limit=50,
        program_id="00000000-0000-0000-0000-000000000001",
        idle_exit_after=2,
        poll_seconds=0.5,
        sleep=slept.append,
    )

    assert result.scanned == 2
    assert result.enqueued == 2
    assert result.skipped == 0
    assert result.empty == 2
    assert result.iterations == 3
    assert slept == [0.5]
    assert enqueuer.calls == [
        (50, "00000000-0000-0000-0000-000000000001"),
        (50, "00000000-0000-0000-0000-000000000001"),
        (50, "00000000-0000-0000-0000-000000000001"),
    ]


def test_raw_artifact_enqueue_loop_is_not_exposed_as_dedicated_compose_service() -> None:
    main_source = graph_projector_cli_source()
    compose_source = Path("docker-compose.yml").read_text(encoding="utf-8")

    assert 'subparsers.add_parser("enqueue-raw-artifacts-loop"' in main_source
    assert "RawArtifactEnqueueLoopResult" in main_source
    assert "graph-projector-raw-artifact-enqueuer" not in compose_source
    assert 'command: ["enqueue-raw-artifacts-loop"]' not in compose_source
