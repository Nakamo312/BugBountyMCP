from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest


def _graph_writer_symbols():
    import sys

    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.contracts import GraphEdgeFact, GraphFactBatch, GraphNodeFact
    from graph_projector.ontology import default_graph_ontology
    from graph_projector.writer import GraphFactWriter, GraphOntologyRegistry

    return GraphNodeFact, GraphEdgeFact, GraphFactBatch, default_graph_ontology, GraphOntologyRegistry, GraphFactWriter


@dataclass(frozen=True)
class RecordedCall:
    query: str
    parameters: dict[str, object]


class RecordingSession:
    def __init__(self, *, edge_records: list[dict[str, object]] | None = None) -> None:
        self.calls: list[RecordedCall] = []
        self.edge_records = edge_records if edge_records is not None else [{"identity_key": "edge-written"}]

    def run(self, query: str, parameters: dict[str, object] | None = None):
        self.calls.append(RecordedCall(query=query, parameters=parameters or {}))
        if "RETURN rel.identity_key AS identity_key" in query:
            return list(self.edge_records)
        return []


def test_graph_edge_identity_key_includes_program_id() -> None:
    _, GraphEdgeFact, _, _, _, _ = _graph_writer_symbols()

    program_id = uuid4()
    fact = GraphEdgeFact(
        program_id=program_id,
        edge_kind="RESOLVES_TO",
        src_kind="Host",
        src_key="api.example.com",
        dst_kind="IP",
        dst_key="203.0.113.10",
        producer="dnsx",
        source_artifact_id=uuid4(),
        tool_run_id=uuid4(),
        confidence=0.95,
    )

    assert fact.identity_key == (
        f"edge:{program_id}:Host:api.example.com:RESOLVES_TO:IP:203.0.113.10"
    )


def test_ontology_registry_validates_facts_without_loading_yaml_per_batch() -> None:
    GraphNodeFact, GraphEdgeFact, GraphFactBatch, default_graph_ontology, GraphOntologyRegistry, _ = (
        _graph_writer_symbols()
    )

    program_id = uuid4()
    registry = GraphOntologyRegistry(default_graph_ontology())
    artifact_id = uuid4()
    tool_run_id = uuid4()
    batch = GraphFactBatch(
        program_id=program_id,
        produced_by="dnsx-parser",
        parser_version="1.0.0",
        facts=[
            GraphNodeFact(
                program_id=program_id,
                kind="Host",
                key="api.example.com",
                producer="httpx",
                source_artifact_id=artifact_id,
                tool_run_id=tool_run_id,
                confidence=0.9,
            ),
            GraphNodeFact(
                program_id=program_id,
                kind="IP",
                key="203.0.113.10",
                producer="dnsx",
                source_artifact_id=artifact_id,
                tool_run_id=tool_run_id,
                confidence=0.95,
            ),
            GraphEdgeFact(
                program_id=program_id,
                edge_kind="RESOLVES_TO",
                src_kind="Host",
                src_key="api.example.com",
                dst_kind="IP",
                dst_key="203.0.113.10",
                producer="dnsx",
                source_artifact_id=artifact_id,
                tool_run_id=tool_run_id,
                confidence=0.95,
            ),
        ],
    )

    registry.validate_batch(batch)

    wrong_edge = GraphEdgeFact(
        program_id=program_id,
        edge_kind="RESOLVES_TO",
        src_kind="Endpoint",
        src_key="https://api.example.com/",
        dst_kind="IP",
        dst_key="203.0.113.10",
        producer="dnsx",
        source_artifact_id=artifact_id,
        tool_run_id=tool_run_id,
        confidence=0.95,
    )
    with pytest.raises(ValueError):
        registry.validate_edge_fact(wrong_edge)


def test_graph_fact_writer_merges_nodes_and_edges_without_creating_edge_endpoints() -> None:
    GraphNodeFact, GraphEdgeFact, GraphFactBatch, default_graph_ontology, GraphOntologyRegistry, GraphFactWriter = (
        _graph_writer_symbols()
    )

    program_id = uuid4()
    artifact_id = uuid4()
    tool_run_id = uuid4()
    registry = GraphOntologyRegistry(default_graph_ontology())
    writer = GraphFactWriter(registry)
    session = RecordingSession()
    edge = GraphEdgeFact(
        program_id=program_id,
        edge_kind="RESOLVES_TO",
        src_kind="Host",
        src_key="api.example.com",
        dst_kind="IP",
        dst_key="203.0.113.10",
        producer="dnsx",
        source_artifact_id=artifact_id,
        tool_run_id=tool_run_id,
        confidence=0.95,
    )
    batch = GraphFactBatch(
        program_id=program_id,
        produced_by="dnsx-parser",
        parser_version="1.0.0",
        facts=[
            GraphNodeFact(
                program_id=program_id,
                kind="Host",
                key="api.example.com",
                producer="httpx",
                source_artifact_id=artifact_id,
                tool_run_id=tool_run_id,
                confidence=0.9,
            ),
            GraphNodeFact(
                program_id=program_id,
                kind="IP",
                key="203.0.113.10",
                producer="dnsx",
                source_artifact_id=artifact_id,
                tool_run_id=tool_run_id,
                confidence=0.95,
            ),
            edge,
        ],
    )

    result = writer.write_batch(session, batch)

    assert result.nodes_written == 2
    assert result.edges_written == 1
    assert result.edges_skipped == 0
    queries = "\n".join(call.query for call in session.calls)
    assert "MERGE (node:Host" in queries
    assert "MERGE (node:IP" in queries
    assert "MATCH (src:Host" in queries
    assert "MATCH (dst:IP" in queries
    assert "MERGE (src)-[rel:RESOLVES_TO" in queries
    assert all(call.parameters.get("program_id") == str(program_id) for call in session.calls)
    assert any(call.parameters.get("identity_key") == edge.identity_key for call in session.calls)




def test_graph_fact_writer_counts_edge_as_skipped_when_endpoints_are_missing() -> None:
    GraphNodeFact, GraphEdgeFact, GraphFactBatch, default_graph_ontology, GraphOntologyRegistry, GraphFactWriter = (
        _graph_writer_symbols()
    )

    program_id = uuid4()
    artifact_id = uuid4()
    tool_run_id = uuid4()
    registry = GraphOntologyRegistry(default_graph_ontology())
    writer = GraphFactWriter(registry)
    session = RecordingSession(edge_records=[])
    edge = GraphEdgeFact(
        program_id=program_id,
        edge_kind="RESOLVES_TO",
        src_kind="Host",
        src_key="missing.example.com",
        dst_kind="IP",
        dst_key="203.0.113.10",
        producer="dnsx",
        source_artifact_id=artifact_id,
        tool_run_id=tool_run_id,
        confidence=0.95,
    )
    batch = GraphFactBatch(
        program_id=program_id,
        produced_by="dnsx-parser",
        parser_version="1.0.0",
        facts=[edge],
    )

    result = writer.write_batch(session, batch)

    assert result.nodes_written == 0
    assert result.edges_written == 0
    assert result.edges_skipped == 1
    assert "RETURN rel.identity_key AS identity_key" in session.calls[0].query

def test_graph_fact_writer_normalizes_neo4j_safe_properties() -> None:
    GraphNodeFact, _, GraphFactBatch, default_graph_ontology, GraphOntologyRegistry, GraphFactWriter = (
        _graph_writer_symbols()
    )

    program_id = uuid4()
    artifact_id = uuid4()
    tool_run_id = uuid4()
    registry = GraphOntologyRegistry(default_graph_ontology())
    writer = GraphFactWriter(registry)
    session = RecordingSession()
    extra_id = uuid4()
    observed_at = datetime(2026, 1, 1, 12, 30, tzinfo=timezone.utc)
    node = GraphNodeFact(
        program_id=program_id,
        kind="Artifact",
        key=str(artifact_id),
        producer="raw-artifact-metadata",
        source_artifact_id=artifact_id,
        tool_run_id=tool_run_id,
        confidence=1.0,
        properties={
            "artifact_id": extra_id,
            "created_at": observed_at,
            "tags": ["raw", "httpx"],
            "job_id": None,
        },
    )
    batch = GraphFactBatch(
        program_id=program_id,
        produced_by="raw-artifact-metadata",
        parser_version="raw-artifact-metadata.v1",
        facts=[node],
    )

    writer.write_batch(session, batch)

    properties = session.calls[0].parameters["properties"]
    assert properties["artifact_id"] == str(extra_id)
    assert properties["created_at"] == observed_at.isoformat()
    assert properties["tags"] == ["raw", "httpx"]
    assert "job_id" not in properties


def test_graph_fact_writer_rejects_nested_properties_before_writing() -> None:
    GraphNodeFact, _, GraphFactBatch, default_graph_ontology, GraphOntologyRegistry, GraphFactWriter = (
        _graph_writer_symbols()
    )

    program_id = uuid4()
    artifact_id = uuid4()
    tool_run_id = uuid4()
    registry = GraphOntologyRegistry(default_graph_ontology())
    writer = GraphFactWriter(registry)
    session = RecordingSession()
    node = GraphNodeFact(
        program_id=program_id,
        kind="Artifact",
        key=str(artifact_id),
        producer="raw-artifact-metadata",
        source_artifact_id=artifact_id,
        tool_run_id=tool_run_id,
        confidence=1.0,
        properties={"metadata": {"runner": "httpx"}},
    )
    batch = GraphFactBatch(
        program_id=program_id,
        produced_by="raw-artifact-metadata",
        parser_version="raw-artifact-metadata.v1",
        facts=[node],
    )

    with pytest.raises(ValueError, match="unsupported Neo4j property"):
        writer.write_batch(session, batch)

    assert session.calls == []

def test_graph_fact_writer_has_no_canonical_origin_write_path() -> None:
    source = Path("services/graph-projector/graph_projector/writer.py").read_text(encoding="utf-8")

    assert "source_table" not in source
    assert "source_record_id" not in source
    assert "source_tables" not in source
    assert "source_record_ids" not in source


def test_graph_fact_writer_does_not_load_ontology_yaml_inside_write_path() -> None:
    source = Path("services/graph-projector/graph_projector/writer.py").read_text(encoding="utf-8")

    assert "load_graph_ontology" not in source
    assert "default_graph_ontology" not in source
    assert "ontology.yaml" not in source


def test_graph_fact_writer_replaces_action_outcome_derived_edges_before_reprojecting() -> None:
    GraphNodeFact, GraphEdgeFact, GraphFactBatch, default_graph_ontology, GraphOntologyRegistry, GraphFactWriter = (
        _graph_writer_symbols()
    )

    program_id = uuid4()
    outcome_id = uuid4()
    registry = GraphOntologyRegistry(default_graph_ontology())
    writer = GraphFactWriter(registry)
    session = RecordingSession()
    batch = GraphFactBatch(
        program_id=program_id,
        produced_by="action-outcome-memory",
        parser_version="action-outcome-memory.v1",
        facts=[
            GraphNodeFact(
                program_id=program_id,
                kind="ActionOutcome",
                key=str(outcome_id),
                producer="action-outcome-memory",
                tool_run_id=uuid4(),
                confidence=1.0,
                properties={"information_gain_score": 4.0},
            ),
            GraphNodeFact(
                program_id=program_id,
                kind="OutcomeFeature",
                key="information_gain_bucket:1-5",
                producer="action-outcome-memory",
                tool_run_id=uuid4(),
                confidence=1.0,
                properties={"feature_type": "information_gain_bucket", "feature_value": "1-5"},
            ),
            GraphEdgeFact(
                program_id=program_id,
                src_kind="ActionOutcome",
                src_key=str(outcome_id),
                edge_kind="HAS_OUTCOME_FEATURE",
                dst_kind="OutcomeFeature",
                dst_key="information_gain_bucket:1-5",
                producer="action-outcome-memory",
                tool_run_id=uuid4(),
                confidence=1.0,
            ),
        ],
    )

    result = writer.write_batch(session, batch)

    assert result.nodes_written == 2
    assert result.edges_written == 1
    assert "DELETE rel" in session.calls[0].query
    assert "HAS_OUTCOME_FEATURE" in session.calls[0].query
    assert "BEFORE_SURFACE_SNAPSHOT" in session.calls[0].query
    assert "AFTER_SURFACE_SNAPSHOT" in session.calls[0].query
    assert session.calls[0].parameters == {"program_id": str(program_id), "key": str(outcome_id)}
    assert "MERGE (node:ActionOutcome" in session.calls[1].query


def test_graph_fact_writer_does_not_refresh_append_only_nodes() -> None:
    GraphNodeFact, _, GraphFactBatch, default_graph_ontology, GraphOntologyRegistry, GraphFactWriter = (
        _graph_writer_symbols()
    )

    program_id = uuid4()
    registry = GraphOntologyRegistry(default_graph_ontology())
    writer = GraphFactWriter(registry)
    session = RecordingSession()
    batch = GraphFactBatch(
        program_id=program_id,
        produced_by="raw-artifact-metadata",
        parser_version="raw-artifact-metadata.v1",
        facts=[
            GraphNodeFact(
                program_id=program_id,
                kind="Artifact",
                key=str(uuid4()),
                producer="raw-artifact-metadata",
                source_artifact_id=uuid4(),
                confidence=1.0,
            ),
        ],
    )

    writer.write_batch(session, batch)

    assert len(session.calls) == 1
    assert "DELETE rel" not in session.calls[0].query
