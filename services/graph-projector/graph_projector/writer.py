from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Protocol
from uuid import UUID

from .contracts import GraphEdgeFact, GraphFactBatch, GraphNodeFact
from .ontology import GraphOntology, GraphRelationshipDefinition


class Neo4jSession(Protocol):
    def run(self, query: str, parameters: dict[str, object] | None = None) -> object: ...


@dataclass(frozen=True)
class GraphFactWriteResult:
    nodes_written: int = 0
    edges_written: int = 0
    edges_skipped: int = 0


class GraphOntologyRegistry:
    def __init__(self, ontology: GraphOntology) -> None:
        self._node_labels = {definition.label for definition in ontology.node_definitions}
        self._relationships: dict[str, GraphRelationshipDefinition] = {
            definition.relationship_type: definition for definition in ontology.relationship_definitions
        }

    def validate_batch(self, batch: GraphFactBatch) -> None:
        for fact in batch.facts:
            if isinstance(fact, GraphNodeFact):
                self.validate_node_fact(fact)
            else:
                self.validate_edge_fact(fact)

    def validate_node_fact(self, fact: GraphNodeFact) -> None:
        if fact.kind not in self._node_labels:
            raise ValueError(f"unknown graph node label: {fact.kind}")

    def validate_edge_fact(self, fact: GraphEdgeFact) -> None:
        relationship = self._relationships.get(fact.edge_kind)
        if relationship is None:
            raise ValueError(f"unknown graph relationship type: {fact.edge_kind}")
        if fact.src_kind not in relationship.source_labels:
            raise ValueError(f"invalid source label {fact.src_kind} for {fact.edge_kind}")
        if fact.dst_kind not in relationship.target_labels:
            raise ValueError(f"invalid target label {fact.dst_kind} for {fact.edge_kind}")


class GraphFactWriter:
    def __init__(self, registry: GraphOntologyRegistry) -> None:
        self._registry = registry

    def write_batch(self, session: Neo4jSession, batch: GraphFactBatch) -> GraphFactWriteResult:
        self._registry.validate_batch(batch)

        nodes_written = 0
        edges_written = 0
        edges_skipped = 0
        for fact in batch.facts:
            if isinstance(fact, GraphNodeFact):
                session.run(_node_merge_query(fact.kind), _node_parameters(fact))
                nodes_written += 1
            else:
                result = session.run(_edge_merge_query(fact), _edge_parameters(fact))
                if _edge_result_has_record(result):
                    edges_written += 1
                else:
                    edges_skipped += 1
        return GraphFactWriteResult(
            nodes_written=nodes_written,
            edges_written=edges_written,
            edges_skipped=edges_skipped,
        )


def _node_merge_query(label: str) -> str:
    safe_label = _safe_cypher_name(label)
    return f"""
MERGE (node:{safe_label} {{program_id: $program_id, key: $key}})
ON CREATE SET node.first_seen = datetime()
SET node.last_seen = datetime(),
    node.identity_key = $identity_key,
    node.confidence = CASE
        WHEN node.confidence IS NULL OR node.confidence < $confidence THEN $confidence
        ELSE node.confidence
    END,
    node.producers = CASE
        WHEN node.producers IS NULL THEN [$producer]
        WHEN NOT $producer IN node.producers THEN node.producers + $producer
        ELSE node.producers
    END,
    node.source_artifact_ids = CASE
        WHEN $source_artifact_id IS NULL THEN coalesce(node.source_artifact_ids, [])
        WHEN node.source_artifact_ids IS NULL THEN [$source_artifact_id]
        WHEN NOT $source_artifact_id IN node.source_artifact_ids THEN node.source_artifact_ids + $source_artifact_id
        ELSE node.source_artifact_ids
    END,
    node.tool_run_ids = CASE
        WHEN $tool_run_id IS NULL THEN coalesce(node.tool_run_ids, [])
        WHEN node.tool_run_ids IS NULL THEN [$tool_run_id]
        WHEN NOT $tool_run_id IN node.tool_run_ids THEN node.tool_run_ids + $tool_run_id
        ELSE node.tool_run_ids
    END
SET node += $properties
""".strip()


def _edge_merge_query(edge: GraphEdgeFact) -> str:
    source_label = _safe_cypher_name(edge.src_kind)
    target_label = _safe_cypher_name(edge.dst_kind)
    relationship_type = _safe_cypher_name(edge.edge_kind)
    return f"""
MATCH (src:{source_label} {{program_id: $program_id, key: $src_key}})
MATCH (dst:{target_label} {{program_id: $program_id, key: $dst_key}})
MERGE (src)-[rel:{relationship_type} {{identity_key: $identity_key}}]->(dst)
ON CREATE SET rel.first_seen = datetime()
SET rel.last_seen = datetime(),
    rel.program_id = $program_id,
    rel.confidence = CASE
        WHEN rel.confidence IS NULL OR rel.confidence < $confidence THEN $confidence
        ELSE rel.confidence
    END,
    rel.producers = CASE
        WHEN rel.producers IS NULL THEN [$producer]
        WHEN NOT $producer IN rel.producers THEN rel.producers + $producer
        ELSE rel.producers
    END,
    rel.source_artifact_ids = CASE
        WHEN $source_artifact_id IS NULL THEN coalesce(rel.source_artifact_ids, [])
        WHEN rel.source_artifact_ids IS NULL THEN [$source_artifact_id]
        WHEN NOT $source_artifact_id IN rel.source_artifact_ids THEN rel.source_artifact_ids + $source_artifact_id
        ELSE rel.source_artifact_ids
    END,
    rel.tool_run_ids = CASE
        WHEN $tool_run_id IS NULL THEN coalesce(rel.tool_run_ids, [])
        WHEN rel.tool_run_ids IS NULL THEN [$tool_run_id]
        WHEN NOT $tool_run_id IN rel.tool_run_ids THEN rel.tool_run_ids + $tool_run_id
        ELSE rel.tool_run_ids
    END
SET rel += $properties
RETURN rel.identity_key AS identity_key
""".strip()


def _edge_result_has_record(result: object) -> bool:
    single = getattr(result, "single", None)
    if callable(single):
        try:
            return single(strict=False) is not None
        except TypeError:
            return single() is not None
    if isinstance(result, list):
        return bool(result)
    try:
        return bool(next(iter(result)))  # type: ignore[arg-type]
    except StopIteration:
        return False
    except TypeError:
        return True


def _node_parameters(node: GraphNodeFact) -> dict[str, object]:
    return {
        "program_id": str(node.program_id),
        "key": node.key,
        "identity_key": node.identity_key,
        "producer": node.producer,
        "source_artifact_id": _optional_uuid(node.source_artifact_id),
        "tool_run_id": _optional_uuid(node.tool_run_id),
        "confidence": node.confidence,
        "properties": _properties(node.properties),
    }


def _edge_parameters(edge: GraphEdgeFact) -> dict[str, object]:
    return {
        "program_id": str(edge.program_id),
        "src_key": edge.src_key,
        "dst_key": edge.dst_key,
        "identity_key": edge.identity_key,
        "producer": edge.producer,
        "source_artifact_id": _optional_uuid(edge.source_artifact_id),
        "tool_run_id": _optional_uuid(edge.tool_run_id),
        "confidence": edge.confidence,
        "properties": _properties(edge.properties),
    }


def _optional_uuid(value: UUID | None) -> str | None:
    return str(value) if value is not None else None


def _properties(properties: dict[str, Any]) -> dict[str, object]:
    reserved = {
        "program_id",
        "key",
        "identity_key",
        "producer",
        "producers",
        "source_artifact_id",
        "source_artifact_ids",
        "tool_run_id",
        "tool_run_ids",
        "confidence",
        "first_seen",
        "last_seen",
    }
    normalized: dict[str, object] = {}
    for key, value in properties.items():
        if key in reserved or value is None:
            continue
        safe_key = _safe_property_key(key)
        normalized[safe_key] = _neo4j_value(value, path=key)
    return normalized


def _neo4j_value(value: Any, *, path: str) -> object:
    if value is None:
        raise ValueError(f"unsupported Neo4j property {path}: null values are omitted only at the top level")
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, (list, tuple, set)):
        return [_neo4j_list_value(item, path=path) for item in value]
    raise ValueError(f"unsupported Neo4j property {path}: {type(value).__name__}")


def _neo4j_list_value(value: Any, *, path: str) -> object:
    if isinstance(value, (dict, list, tuple, set)) or value is None:
        raise ValueError(f"unsupported Neo4j property {path}: nested or null list values are not supported")
    return _neo4j_value(value, path=path)


def _safe_property_key(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", value):
        raise ValueError(f"unsupported Neo4j property key: {value}")
    return value


def _safe_cypher_name(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", value):
        raise ValueError(f"unsafe cypher identifier: {value}")
    return value
