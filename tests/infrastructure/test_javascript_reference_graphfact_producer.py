from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from tests.infrastructure.graph_projector_cli_test_helpers import graph_projector_cli_source


def _symbols():
    import sys

    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.producers.javascript_references import (
        JavaScriptReferenceGraphFactProducer,
        javascript_reference_dedupe_key,
        js_file_key,
    )

    return JavaScriptReferenceGraphFactProducer, javascript_reference_dedupe_key, js_file_key


def _enqueue_symbols():
    import sys

    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.producers.javascript_references import (
        JavaScriptReferenceGraphFactEnqueuer,
        JavaScriptReferenceGraphFactProducer,
        javascript_reference_dedupe_key,
    )

    return JavaScriptReferenceGraphFactEnqueuer, JavaScriptReferenceGraphFactProducer, javascript_reference_dedupe_key


def _reference_row(**overrides):
    program_id = overrides.pop("program_id", uuid4())
    run_id = overrides.pop("run_id", uuid4())
    raw_artifact_id = overrides.pop("raw_artifact_id", uuid4())
    row = {
        "javascript_reference_id": uuid4(),
        "program_id": program_id,
        "run_id": run_id,
        "raw_artifact_id": raw_artifact_id,
        "source_tool": "linkfinder",
        "source_url": "https://app.example.com/static/app.js?v=123",
        "referenced_url": "https://api.example.com/v1/users/123?token=secret",
        "reference_type": "endpoint",
        "observed_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "endpoint_id": uuid4(),
        "path": "/v1/users/123",
        "normalized_path": "/v1/users/{id}",
        "host_id": uuid4(),
        "hostname": "api.example.com",
        "service_id": uuid4(),
        "scheme": "https",
        "port": 443,
        "ip_id": uuid4(),
        "ip_address": "203.0.113.10",
    }
    row.update(overrides)
    return row


def test_javascript_reference_producer_projects_jsfile_references_endpoint_with_evidence_path() -> None:
    JavaScriptReferenceGraphFactProducer, _, js_file_key_fn = _symbols()
    row = _reference_row()

    batch = JavaScriptReferenceGraphFactProducer().produce([row])

    assert batch is not None
    assert batch.program_id == row["program_id"]
    assert batch.produced_by == "javascript-reference-producer"

    node_facts = {(fact.kind, fact.key): fact for fact in batch.facts if hasattr(fact, "kind")}
    edge_facts = {
        (fact.src_kind, fact.src_key, fact.edge_kind, fact.dst_kind, fact.dst_key): fact
        for fact in batch.facts
        if hasattr(fact, "edge_kind")
    }

    js_key = js_file_key_fn(row["source_url"])
    endpoint_key = "api.example.com:443/https:GET:/v1/users/{id}"

    assert ("JSFile", js_key) in node_facts
    assert node_facts[("JSFile", js_key)].properties == {
        "url": "https://app.example.com/static/app.js",
        "hostname": "app.example.com",
        "path": "/static/app.js",
    }
    assert ("Endpoint", endpoint_key) in node_facts
    assert ("Artifact", str(row["raw_artifact_id"])) in node_facts
    assert ("Observation", str(row["javascript_reference_id"])) in node_facts

    assert ("JSFile", js_key, "REFERENCES", "Endpoint", endpoint_key) in edge_facts
    assert ("Artifact", str(row["raw_artifact_id"]), "PRODUCED_OBSERVATION", "Observation", str(row["javascript_reference_id"])) in edge_facts
    assert ("Observation", str(row["javascript_reference_id"]), "DESCRIBES", "JSFile", js_key) in edge_facts
    assert ("Observation", str(row["javascript_reference_id"]), "DESCRIBES", "Endpoint", endpoint_key) in edge_facts

    projected_values = str([fact.properties for fact in batch.facts])
    assert "token=secret" not in projected_values
    assert "/v1/users/123?token=secret" not in projected_values


def test_javascript_reference_producer_requires_source_lineage() -> None:
    JavaScriptReferenceGraphFactProducer, *_ = _symbols()
    producer = JavaScriptReferenceGraphFactProducer()

    assert producer.produce([_reference_row(raw_artifact_id=None)]) is None
    assert producer.produce([_reference_row(run_id=None)]) is None


def test_javascript_reference_producer_accepts_new_source_tools_for_canonical_rows() -> None:
    JavaScriptReferenceGraphFactProducer, *_ = _symbols()

    batch = JavaScriptReferenceGraphFactProducer().produce([_reference_row(source_tool="custom-js-finder")])

    assert batch is not None
    assert {fact.producer for fact in batch.facts} == {"custom-js-finder"}


def test_javascript_reference_dedupe_key_is_stable() -> None:
    _, dedupe_key, _ = _symbols()
    raw_artifact_id = uuid4()

    assert dedupe_key(raw_artifact_id, "javascript-references.v1") == (
        f"javascript-references:{raw_artifact_id}:javascript-references.v1"
    )


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

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.commits += 1


class RecordingBatchStore:
    def __init__(self) -> None:
        self.calls: list[tuple[object, str | None]] = []

    def enqueue(self, batch, *, dedupe_key: str | None = None):
        self.calls.append((batch, dedupe_key))
        return uuid4()


def test_javascript_reference_enqueuer_reads_canonical_rows_from_projection_events() -> None:
    JavaScriptReferenceGraphFactEnqueuer, JavaScriptReferenceGraphFactProducer, dedupe_key = _enqueue_symbols()
    projection_event_id = uuid4()
    raw_artifact_id = uuid4()
    row = _reference_row(
        projection_event_id=projection_event_id,
        projection_event_attempts=1,
        event_raw_artifact_id=raw_artifact_id,
        raw_artifact_id=raw_artifact_id,
    )
    connection = RecordingConnection([row])
    store = RecordingBatchStore()
    enqueuer = JavaScriptReferenceGraphFactEnqueuer(
        connection=connection,
        store=store,
        producer=JavaScriptReferenceGraphFactProducer(),
    )

    result = enqueuer.enqueue_pending(limit=10, program_id=row["program_id"])

    claim_query, claim_parameters = connection.cursor_obj.calls[0]
    assert result.scanned == 1
    assert result.enqueued == 1
    assert "event_type = 'javascript_references_ready'" in claim_query
    assert "LEFT JOIN javascript_references jr" in claim_query
    assert "raw_artifacts" not in claim_query
    assert "jr.source_tool IS NOT NULL" in claim_query
    assert "jr.source_tool != ''" in claim_query
    assert "source_tool = ANY" not in claim_query
    assert "source_tools" not in claim_parameters
    assert store.calls[0][1] == dedupe_key(raw_artifact_id, "javascript-references.v1")


def test_javascript_reference_enqueue_loop_is_not_exposed_as_dedicated_compose_service() -> None:
    main_source = graph_projector_cli_source()
    settings_source = Path("services/graph-projector/graph_projector/settings.py").read_text(encoding="utf-8")
    compose_source = Path("docker-compose.yml").read_text(encoding="utf-8")

    assert 'subparsers.add_parser("enqueue-javascript-references"' in main_source
    assert 'subparsers.add_parser("enqueue-javascript-references-loop"' in main_source
    assert "JavaScriptReferenceGraphFactEnqueuer" in main_source
    assert "JavaScriptReferenceEnqueueLoopResult" in main_source
    assert "javascript_reference_enqueue_limit" in settings_source
    assert "JAVASCRIPT_REFERENCE_ENQUEUE_LIMIT" in settings_source
    assert "javascript_reference_enqueue_poll_seconds" in settings_source
    assert "JAVASCRIPT_REFERENCE_ENQUEUE_POLL_SECONDS" in settings_source
    assert 'subparsers.add_parser("enqueue-canonical-facts-loop"' not in main_source
    assert "graph-projector-canonical-fact-enqueuer" not in compose_source
    assert "graph-projector-javascript-reference-enqueuer" not in compose_source
    assert "JAVASCRIPT_REFERENCE_ENQUEUE_LIMIT" not in compose_source
    assert "JAVASCRIPT_REFERENCE_ENQUEUE_POLL_SECONDS" not in compose_source
    assert 'command: ["enqueue-javascript-references-loop"]' not in compose_source


def test_graph_projector_settings_parse_javascript_reference_enqueue_controls(monkeypatch) -> None:
    import sys

    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.settings import GraphProjectorSettings

    monkeypatch.setenv("JAVASCRIPT_REFERENCE_ENQUEUE_LIMIT", "25")
    monkeypatch.setenv("JAVASCRIPT_REFERENCE_ENQUEUE_POLL_SECONDS", "0.25")

    settings = GraphProjectorSettings.from_env()

    assert settings.javascript_reference_enqueue_limit == 25
    assert settings.javascript_reference_enqueue_poll_seconds == 0.25
