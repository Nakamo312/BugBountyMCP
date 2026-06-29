from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError


def _graph_contracts():
    import sys

    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.contracts import GraphEdgeFact, GraphFactBatch, GraphNodeFact

    return GraphNodeFact, GraphEdgeFact, GraphFactBatch


def test_graph_node_fact_requires_deterministic_identity_and_evidence_lineage() -> None:
    GraphNodeFact, _, _ = _graph_contracts()

    program_id = uuid4()
    artifact_id = uuid4()
    tool_run_id = uuid4()

    fact = GraphNodeFact(
        program_id=program_id,
        kind="Host",
        key="api.example.com",
        producer="httpx",
        source_artifact_id=artifact_id,
        tool_run_id=tool_run_id,
        confidence=0.85,
        properties={"hostname": "api.example.com"},
    )

    assert fact.identity_key == "node:Host:api.example.com"
    assert fact.program_id == program_id
    assert fact.source_artifact_id == artifact_id
    assert fact.tool_run_id == tool_run_id


def test_graph_fact_allows_canonical_inventory_without_artifact_lineage() -> None:
    GraphNodeFact, _, _ = _graph_contracts()

    fact = GraphNodeFact(
        program_id=uuid4(),
        kind="Host",
        key="api.example.com",
        producer="canonical-inventory",
        confidence=1.0,
        properties={"source_table": "hosts"},
    )

    assert fact.source_artifact_id is None
    assert fact.tool_run_id is None


def test_graph_fact_rejects_unknown_top_level_origin_fields() -> None:
    GraphNodeFact, _, _ = _graph_contracts()

    with pytest.raises(ValidationError):
        GraphNodeFact(
            program_id=uuid4(),
            kind="Host",
            key="api.example.com",
            producer="postgres",
            source_table="hosts",
            source_record_id=uuid4(),
            confidence=1.0,
        )


def test_graph_edge_fact_requires_stable_endpoints_and_evidence_lineage() -> None:
    _, GraphEdgeFact, _ = _graph_contracts()

    program_id = uuid4()
    artifact_id = uuid4()
    tool_run_id = uuid4()

    fact = GraphEdgeFact(
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

    assert fact.identity_key == (
        f"edge:{program_id}:Host:api.example.com:RESOLVES_TO:IP:203.0.113.10"
    )
    assert fact.program_id == program_id
    assert fact.source_artifact_id == artifact_id
    assert fact.tool_run_id == tool_run_id


def test_graph_fact_batch_uses_single_fact_list_with_parser_metadata() -> None:
    GraphNodeFact, GraphEdgeFact, GraphFactBatch = _graph_contracts()

    program_id = uuid4()
    artifact_id = uuid4()
    tool_run_id = uuid4()

    node = GraphNodeFact(
        program_id=program_id,
        kind="Host",
        key="api.example.com",
        producer="httpx",
        source_artifact_id=artifact_id,
        tool_run_id=tool_run_id,
        confidence=0.9,
    )
    edge = GraphEdgeFact(
        program_id=program_id,
        edge_kind="OBSERVED_BY",
        src_kind="Host",
        src_key="api.example.com",
        dst_kind="ToolRun",
        dst_key=str(tool_run_id),
        producer="httpx",
        source_artifact_id=artifact_id,
        tool_run_id=tool_run_id,
        confidence=1.0,
    )

    batch = GraphFactBatch(
        program_id=program_id,
        facts=[node, edge],
        produced_by="httpx-parser",
        parser_version="1.0.0",
    )
    assert batch.program_id == program_id
    assert batch.facts == [node, edge]
    assert batch.produced_by == "httpx-parser"
    assert batch.parser_version == "1.0.0"

    with pytest.raises(ValidationError):
        GraphFactBatch(program_id=program_id, facts=[], produced_by="httpx-parser", parser_version="1.0.0")

    other_program_node = GraphNodeFact(
        program_id=uuid4(),
        kind="Host",
        key="other.example.com",
        producer="httpx",
        source_artifact_id=artifact_id,
        tool_run_id=tool_run_id,
        confidence=0.9,
    )
    with pytest.raises(ValidationError):
        GraphFactBatch(
            program_id=program_id,
            facts=[node, other_program_node],
            produced_by="httpx-parser",
            parser_version="1.0.0",
        )


def test_graph_fact_batch_rejects_missing_parser_metadata() -> None:
    GraphNodeFact, _, GraphFactBatch = _graph_contracts()

    program_id = uuid4()
    node = GraphNodeFact(
        program_id=program_id,
        kind="Host",
        key="api.example.com",
        producer="httpx",
        source_artifact_id=uuid4(),
        tool_run_id=uuid4(),
        confidence=0.9,
    )

    with pytest.raises(ValidationError):
        GraphFactBatch(program_id=program_id, facts=[node], parser_version="1.0.0")
    with pytest.raises(ValidationError):
        GraphFactBatch(program_id=program_id, facts=[node], produced_by="httpx-parser")
