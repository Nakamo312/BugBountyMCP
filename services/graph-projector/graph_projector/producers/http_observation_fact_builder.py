from __future__ import annotations

from typing import Any, Mapping
import re
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

from ..contracts import GraphEdgeFact, GraphFactBatch, GraphNodeFact
from .http_observation_keys import parameter_key, request_shape_key, service_key, service_method_normalized_path_key
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
    path_param_names = _path_parameter_names(projection.normalized_path)
    query_param_names = _query_parameter_names(projection.url)
    request_key = request_shape_key(
        endpoint_key=endpoint_key,
        method=projection.method,
        path_params=path_param_names,
        query_params=query_param_names,
    )
    facts = [
        _node(projection, lineage, "Program", str(projection.program_id), {"program_id": str(projection.program_id)}),
        _node(projection, lineage, "Host", projection.hostname, {"hostname": projection.hostname}),
        _node(projection, lineage, "IP", projection.ip_address, {"address": projection.ip_address}),
        _service_node(projection, lineage, svc_key),
        _endpoint_node(projection, lineage, endpoint_key, svc_key),
        _request_shape_node(projection, lineage, request_key, endpoint_key, path_param_names, query_param_names),
        _node(projection, lineage, "Artifact", str(projection.raw_artifact_id), {"artifact_id": str(projection.raw_artifact_id)}),
        _observation_node(projection, lineage, parser_version),
        _evidence_node(projection, lineage),
        _program_asset_edge(projection, lineage, "Host", projection.hostname),
        _program_asset_edge(projection, lineage, "IP", projection.ip_address),
        _program_asset_edge(projection, lineage, "Service", svc_key),
        _program_asset_edge(projection, lineage, "Endpoint", endpoint_key),
        _program_asset_edge(projection, lineage, "RequestShape", request_key),
        _edge(projection, lineage, "Host", projection.hostname, "RESOLVES_TO", "IP", projection.ip_address),
        _edge(projection, lineage, "Host", projection.hostname, "EXPOSES_SERVICE", "Service", svc_key, {"port": projection.port, "scheme": projection.scheme}),
        _edge(projection, lineage, "IP", projection.ip_address, "EXPOSES_SERVICE", "Service", svc_key, {"port": projection.port, "scheme": projection.scheme}),
        _edge(projection, lineage, "Service", svc_key, "HAS_ENDPOINT", "Endpoint", endpoint_key, {"method": projection.method, "status_code": projection.status_code}),
        _edge(projection, lineage, "Endpoint", endpoint_key, "HAS_REQUEST_SHAPE", "RequestShape", request_key, {"method": projection.method}),
        _edge(projection, lineage, "RequestShape", request_key, "SUPPORTED_BY", "Observation", str(projection.observation_id), {"confidence": 1.0}),
        _produced_observation_edge(projection, lineage, parser_version),
        _supports_evidence_edge(projection, lineage),
        _evidence_derived_from_edge(projection, lineage),
        _describes_edge(projection, lineage, "Host", projection.hostname),
        _describes_edge(projection, lineage, "IP", projection.ip_address),
        _describes_edge(projection, lineage, "Service", svc_key),
        _describes_edge(projection, lineage, "Endpoint", endpoint_key),
        _describes_edge(projection, lineage, "RequestShape", request_key),
    ]
    facts.extend(_path_parameter_facts(projection, lineage, endpoint_key, path_param_names))
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
        {
            "service_key": svc_key,
            "port": projection.port,
            "scheme": projection.scheme,
            "hostname": projection.hostname,
            "origin": _origin(projection),
            "display_label": f"{projection.method} service @ {projection.hostname}:{projection.port}",
        },
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
            "hostname": projection.hostname,
            "port": projection.port,
            "scheme": projection.scheme,
            "display_label": _endpoint_display_label(projection),
        },
    )


def _request_shape_node(
    projection: HttpObservationProjection,
    lineage: dict[str, object],
    request_key: str,
    endpoint_key: str,
    path_param_names: tuple[str, ...],
    query_param_names: tuple[str, ...],
) -> GraphNodeFact:
    return _node(
        projection,
        lineage,
        "RequestShape",
        request_key,
        {
            "request_shape_key": request_key,
            "endpoint_key": endpoint_key,
            "method": projection.method,
            "scheme": projection.scheme,
            "hostname": projection.hostname,
            "port": projection.port,
            "normalized_path": projection.normalized_path,
            "path_param_keys": list(path_param_names),
            "query_keys": list(query_param_names),
            "content_type": projection.content_type,
            "status_code": projection.status_code,
            "display_label": _request_shape_display_label(projection, query_param_names),
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


def _evidence_node(projection: HttpObservationProjection, lineage: dict[str, object]) -> GraphNodeFact:
    evidence_id = _evidence_key(projection)
    return _node(
        projection,
        lineage,
        "Evidence",
        evidence_id,
        {
            "evidence_id": evidence_id,
            "claim": _endpoint_display_label(projection),
            "confidence": 1.0,
            "status": "observed",
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


def _program_asset_edge(
    projection: HttpObservationProjection,
    lineage: dict[str, object],
    dst_kind: str,
    dst_key: str,
) -> GraphEdgeFact:
    return _edge(projection, lineage, "Program", str(projection.program_id), "HAS_ASSET", dst_kind, dst_key)


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


def _supports_evidence_edge(projection: HttpObservationProjection, lineage: dict[str, object]) -> GraphEdgeFact:
    return _edge(
        projection,
        lineage,
        "Observation",
        str(projection.observation_id),
        "SUPPORTS_EVIDENCE",
        "Evidence",
        _evidence_key(projection),
        {"confidence": 1.0},
    )


def _evidence_derived_from_edge(projection: HttpObservationProjection, lineage: dict[str, object]) -> GraphEdgeFact:
    return _edge(
        projection,
        lineage,
        "Evidence",
        _evidence_key(projection),
        "DERIVED_FROM",
        "Artifact",
        str(projection.raw_artifact_id),
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


def _path_parameter_facts(
    projection: HttpObservationProjection,
    lineage: dict[str, object],
    endpoint_key: str,
    names: tuple[str, ...],
) -> list[GraphNodeFact | GraphEdgeFact]:
    facts: list[GraphNodeFact | GraphEdgeFact] = []
    for name in names:
        facts.extend(_parameter_fact_triplet(projection, lineage, endpoint_key, "path", name, False))
    return facts


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
            facts.extend(_parameter_fact_triplet(projection, lineage, endpoint_key, "query", name, len(values) > 1))
    return facts


def _parameter_fact_triplet(
    projection: HttpObservationProjection,
    lineage: dict[str, object],
    endpoint_key: str,
    location: str,
    name: str,
    is_array: bool,
) -> list[GraphNodeFact | GraphEdgeFact]:
    key = parameter_key(endpoint_key=endpoint_key, location=location, name=name)
    return [
        _node(
            projection,
            lineage,
            "Parameter",
            key,
            {
                "endpoint_location_name": key,
                "endpoint_key": endpoint_key,
                "location": location,
                "name": name,
                "param_type": "string",
                "display_label": f"{location}:{name} @ {_endpoint_display_label(projection)}",
                "is_array": is_array,
            },
        ),
        _program_asset_edge(projection, lineage, "Parameter", key),
        _edge(projection, lineage, "Endpoint", endpoint_key, "HAS_PARAM", "Parameter", key, {"location": location}),
        _describes_edge(projection, lineage, "Parameter", key),
    ]


def _query_parameter_names(url: str | None) -> tuple[str, ...]:
    if not url:
        return ()
    query = urlsplit(url).query
    if not query:
        return ()
    return tuple(sorted(name.strip() for name in parse_qs(query, keep_blank_values=True) if name.strip()))


def _path_parameter_names(normalized_path: str) -> tuple[str, ...]:
    return tuple(sorted(set(match.group(1).strip() for match in re.finditer(r"\{([^{}]+)\}", normalized_path) if match.group(1).strip())))


def _origin(projection: HttpObservationProjection) -> str:
    suffix = "" if (projection.scheme == "https" and projection.port == 443) or (projection.scheme == "http" and projection.port == 80) else f":{projection.port}"
    return f"{projection.scheme}://{projection.hostname}{suffix}"


def _endpoint_display_label(projection: HttpObservationProjection) -> str:
    return f"{projection.method} {projection.normalized_path} @ {projection.hostname}:{projection.port}"


def _request_shape_display_label(projection: HttpObservationProjection, query_param_names: tuple[str, ...]) -> str:
    suffix = f" ?{','.join(query_param_names)}" if query_param_names else ""
    return f"{projection.method} {projection.normalized_path}{suffix} @ {projection.hostname}:{projection.port}"


def _evidence_key(projection: HttpObservationProjection) -> str:
    return f"http-observation:{projection.observation_id}"
