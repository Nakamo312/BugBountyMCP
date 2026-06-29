from __future__ import annotations

from typing import Any, Mapping
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

from ..contracts import GraphEdgeFact, GraphFactBatch, GraphNodeFact
from .http_observation_keys import parameter_key, service_key, service_method_normalized_path_key
from .http_observation_projection import HttpObservationProjection, http_observation_projection_from_row

PRODUCER_NAME = "http-observation-producer"


def build_http_observation_graph_fact_batch(
    rows: list[Mapping[str, Any]],
    *,
    parser_version: str,
) -> GraphFactBatch | None:
    facts: list[GraphNodeFact | GraphEdgeFact] = []
    seen_fact_keys: set[tuple[str, UUID | None, UUID | None]] = set()
    batch_program_id: UUID | None = None

    for row in rows:
        projection = http_observation_projection_from_row(row)
        if projection is None:
            continue
        batch_program_id = _batch_program_id(batch_program_id, projection.program_id)
        for fact in _http_observation_facts(projection, parser_version=parser_version):
            dedupe_key = (fact.identity_key, fact.source_artifact_id, fact.tool_run_id)
            if dedupe_key in seen_fact_keys:
                continue
            seen_fact_keys.add(dedupe_key)
            facts.append(fact)

    if batch_program_id is None or not facts:
        return None
    return GraphFactBatch(
        program_id=batch_program_id,
        facts=facts,
        produced_by=PRODUCER_NAME,
        parser_version=parser_version,
    )


def _batch_program_id(current: UUID | None, next_program_id: UUID) -> UUID:
    if current is None:
        return next_program_id
    if current != next_program_id:
        raise ValueError("http observation batch cannot mix program_id values")
    return current


def _http_observation_facts(
    projection: HttpObservationProjection,
    *,
    parser_version: str,
) -> list[GraphNodeFact | GraphEdgeFact]:
    svc_key = service_key(hostname=projection.hostname, port=projection.port, scheme=projection.scheme)
    endpoint_key = service_method_normalized_path_key(
        service_key=svc_key,
        method=projection.method,
        normalized_path=projection.normalized_path,
    )
    lineage = _lineage(projection)
    facts = [
        _node(projection, lineage, "Host", projection.hostname, {"hostname": projection.hostname}),
        _node(projection, lineage, "IP", projection.ip_address, {"address": projection.ip_address}),
        _service_node(projection, lineage, svc_key),
        _endpoint_node(projection, lineage, endpoint_key, svc_key),
        _node(projection, lineage, "Artifact", str(projection.raw_artifact_id), {"artifact_id": str(projection.raw_artifact_id)}),
        _observation_node(projection, lineage, parser_version),
        _edge(projection, lineage, "Host", projection.hostname, "RESOLVES_TO", "IP", projection.ip_address),
        _edge(projection, lineage, "IP", projection.ip_address, "EXPOSES_SERVICE", "Service", svc_key),
        _edge(projection, lineage, "Service", svc_key, "HAS_ENDPOINT", "Endpoint", endpoint_key),
        _produced_observation_edge(projection, lineage, parser_version),
        _describes_edge(projection, lineage, "Host", projection.hostname),
        _describes_edge(projection, lineage, "IP", projection.ip_address),
        _describes_edge(projection, lineage, "Service", svc_key),
        _describes_edge(projection, lineage, "Endpoint", endpoint_key),
    ]
    facts.extend(_query_parameter_facts(projection, lineage, endpoint_key))
    return facts


def _lineage(projection: HttpObservationProjection) -> dict[str, object]:
    return {
        "program_id": projection.program_id,
        "producer": projection.source_tool,
        "source_artifact_id": projection.raw_artifact_id,
        "tool_run_id": projection.run_id,
        "confidence": 1.0,
    }


def _node(
    projection: HttpObservationProjection,
    lineage: dict[str, object],
    kind: str,
    key: str,
    properties: dict[str, object],
) -> GraphNodeFact:
    return GraphNodeFact(**lineage, kind=kind, key=key, properties=properties)


def _service_node(projection: HttpObservationProjection, lineage: dict[str, object], svc_key: str) -> GraphNodeFact:
    return _node(
        projection,
        lineage,
        "Service",
        svc_key,
        {"service_key": svc_key, "port": projection.port, "scheme": projection.scheme},
    )


def _endpoint_node(
    projection: HttpObservationProjection,
    lineage: dict[str, object],
    endpoint_key: str,
    svc_key: str,
) -> GraphNodeFact:
    return _node(
        projection,
        lineage,
        "Endpoint",
        endpoint_key,
        {
            "service_method_normalized_path": endpoint_key,
            "service_key": svc_key,
            "method": projection.method,
            "normalized_path": projection.normalized_path,
            "status_code": projection.status_code,
            "content_type": projection.content_type,
            "url": projection.url,
        },
    )


def _observation_node(
    projection: HttpObservationProjection,
    lineage: dict[str, object],
    parser_version: str,
) -> GraphNodeFact:
    return _node(
        projection,
        lineage,
        "Observation",
        str(projection.observation_id),
        {
            "observation_id": str(projection.observation_id),
            "observation_type": "http_observation",
            "confidence": 1.0,
            "parser_version": parser_version,
        },
    )


def _edge(
    projection: HttpObservationProjection,
    lineage: dict[str, object],
    src_kind: str,
    src_key: str,
    edge_kind: str,
    dst_kind: str,
    dst_key: str,
    properties: dict[str, object] | None = None,
) -> GraphEdgeFact:
    return GraphEdgeFact(
        **lineage,
        src_kind=src_kind,
        src_key=src_key,
        edge_kind=edge_kind,
        dst_kind=dst_kind,
        dst_key=dst_key,
        properties=properties or {},
    )


def _produced_observation_edge(
    projection: HttpObservationProjection,
    lineage: dict[str, object],
    parser_version: str,
) -> GraphEdgeFact:
    return _edge(
        projection,
        lineage,
        "Artifact",
        str(projection.raw_artifact_id),
        "PRODUCED_OBSERVATION",
        "Observation",
        str(projection.observation_id),
        {"parser_version": parser_version, "confidence": 1.0},
    )


def _describes_edge(
    projection: HttpObservationProjection,
    lineage: dict[str, object],
    dst_kind: str,
    dst_key: str,
) -> GraphEdgeFact:
    return _edge(
        projection,
        lineage,
        "Observation",
        str(projection.observation_id),
        "DESCRIBES",
        dst_kind,
        dst_key,
        {"confidence": 1.0},
    )


def _query_parameter_facts(
    projection: HttpObservationProjection,
    lineage: dict[str, object],
    endpoint_key: str,
) -> list[GraphNodeFact | GraphEdgeFact]:
    if not projection.url:
        return []
    query = urlsplit(projection.url).query
    if not query:
        return []

    facts: list[GraphNodeFact | GraphEdgeFact] = []
    for raw_name, values in sorted(parse_qs(query, keep_blank_values=True).items()):
        name = raw_name.strip()
        if name:
            facts.extend(_query_parameter_fact_triplet(projection, lineage, endpoint_key, name, len(values) > 1))
    return facts


def _query_parameter_fact_triplet(
    projection: HttpObservationProjection,
    lineage: dict[str, object],
    endpoint_key: str,
    name: str,
    is_array: bool,
) -> list[GraphNodeFact | GraphEdgeFact]:
    key = parameter_key(endpoint_key=endpoint_key, location="query", name=name)
    return [
        _node(
            projection,
            lineage,
            "Parameter",
            key,
            {
                "endpoint_location_name": key,
                "endpoint_key": endpoint_key,
                "location": "query",
                "name": name,
                "param_type": "string",
                "is_array": is_array,
            },
        ),
        _edge(projection, lineage, "Endpoint", endpoint_key, "HAS_PARAM", "Parameter", key, {"location": "query"}),
        _describes_edge(projection, lineage, "Parameter", key),
    ]
