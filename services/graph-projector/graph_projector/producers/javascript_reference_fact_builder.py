from __future__ import annotations

from typing import Any, Mapping
from urllib.parse import urlsplit
from uuid import UUID

from ..contracts import GraphEdgeFact, GraphFactBatch, GraphNodeFact
from .http_observation_keys import service_key, service_method_normalized_path_key
from .http_observation_projection import canonical_hostname
from .javascript_reference_keys import js_file_key
from .javascript_reference_projection import JavaScriptReferenceProjection, javascript_reference_projection_from_row


def build_javascript_reference_graph_fact_batch(
    rows: list[Mapping[str, Any]],
    *,
    parser_version: str,
) -> GraphFactBatch | None:
    facts = []
    batch_program_id: UUID | None = None

    for row in rows:
        projection = javascript_reference_projection_from_row(row)
        if projection is None:
            continue
        batch_program_id = _next_batch_program_id(batch_program_id, projection.program_id)
        facts.extend(_projection_facts(projection, parser_version=parser_version))

    if batch_program_id is None or not facts:
        return None

    return GraphFactBatch(
        program_id=batch_program_id,
        facts=facts,
        produced_by="javascript-reference-producer",
        parser_version=parser_version,
    )


def _next_batch_program_id(current: UUID | None, row_program_id: UUID) -> UUID:
    if current is None:
        return row_program_id
    if current != row_program_id:
        raise ValueError("javascript reference batch cannot mix program_id values")
    return current


def _projection_facts(projection: JavaScriptReferenceProjection, *, parser_version: str) -> list[GraphNodeFact | GraphEdgeFact]:
    js_key = js_file_key(projection.source_url)
    endpoint_key = service_method_normalized_path_key(
        service_key=service_key(hostname=projection.hostname, port=projection.port, scheme=projection.scheme),
        method=projection.method,
        normalized_path=projection.normalized_path,
    )
    lineage = _lineage(projection)
    return [
        _js_file_node(projection, lineage=lineage, js_key=js_key),
        _endpoint_node(projection, lineage=lineage, endpoint_key=endpoint_key),
        _artifact_node(projection, lineage=lineage),
        _observation_node(projection, lineage=lineage, parser_version=parser_version),
        GraphEdgeFact(**lineage, src_kind="JSFile", src_key=js_key, edge_kind="REFERENCES", dst_kind="Endpoint", dst_key=endpoint_key),
        GraphEdgeFact(
            **lineage,
            src_kind="Artifact",
            src_key=str(projection.raw_artifact_id),
            edge_kind="PRODUCED_OBSERVATION",
            dst_kind="Observation",
            dst_key=str(projection.reference_id),
        ),
        GraphEdgeFact(
            **lineage,
            src_kind="Observation",
            src_key=str(projection.reference_id),
            edge_kind="DESCRIBES",
            dst_kind="JSFile",
            dst_key=js_key,
        ),
        GraphEdgeFact(
            **lineage,
            src_kind="Observation",
            src_key=str(projection.reference_id),
            edge_kind="DESCRIBES",
            dst_kind="Endpoint",
            dst_key=endpoint_key,
        ),
    ]


def _lineage(projection: JavaScriptReferenceProjection) -> dict[str, object]:
    return {
        "program_id": projection.program_id,
        "producer": projection.source_tool,
        "source_artifact_id": projection.raw_artifact_id,
        "tool_run_id": projection.run_id,
        "confidence": 1.0,
    }


def _js_file_node(projection: JavaScriptReferenceProjection, *, lineage: dict[str, object], js_key: str) -> GraphNodeFact:
    source_parts = urlsplit(projection.source_url)
    return GraphNodeFact(
        **lineage,
        kind="JSFile",
        key=js_key,
        properties={
            "url": projection.source_url,
            "hostname": canonical_hostname(source_parts.hostname or ""),
            "path": source_parts.path or "/",
        },
    )


def _endpoint_node(projection: JavaScriptReferenceProjection, *, lineage: dict[str, object], endpoint_key: str) -> GraphNodeFact:
    svc_key = service_key(hostname=projection.hostname, port=projection.port, scheme=projection.scheme)
    return GraphNodeFact(
        **lineage,
        kind="Endpoint",
        key=endpoint_key,
        properties={
            "service_method_normalized_path": endpoint_key,
            "service_key": svc_key,
            "method": projection.method,
            "normalized_path": projection.normalized_path,
        },
    )


def _artifact_node(projection: JavaScriptReferenceProjection, *, lineage: dict[str, object]) -> GraphNodeFact:
    return GraphNodeFact(
        **lineage,
        kind="Artifact",
        key=str(projection.raw_artifact_id),
        properties={"artifact_id": str(projection.raw_artifact_id)},
    )


def _observation_node(
    projection: JavaScriptReferenceProjection,
    *,
    lineage: dict[str, object],
    parser_version: str,
) -> GraphNodeFact:
    return GraphNodeFact(
        **lineage,
        kind="Observation",
        key=str(projection.reference_id),
        properties={
            "observation_id": str(projection.reference_id),
            "observation_type": "javascript_reference",
            "reference_type": projection.reference_type,
            "confidence": 1.0,
            "parser_version": parser_version,
        },
    )
