from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
import re
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

from ..contracts import GraphEdgeFact, GraphFactBatch, GraphNodeFact
from .http_observation_keys import (
    parameter_key,
    request_shape_key,
    response_shape_key,
    service_key,
    service_method_normalized_path_key,
    stable_short_hash,
)
from .http_observation_projection import HttpObservationProjection, InputParameterProjection, http_observation_projection_from_row

PRODUCER_NAME = "http-observation-producer"


@dataclass(frozen=True)
class ParameterShape:
    location: str
    name: str
    param_type: str = "string"
    reflected: bool = False
    is_array: bool = False
    source: str = "derived"


def build_http_observation_graph_fact_batch(
    rows: list[Mapping[str, Any]],
    *,
    parser_version: str,
) -> GraphFactBatch | None:
    facts: list[GraphNodeFact | GraphEdgeFact] = []
    seen_fact_keys: set[tuple[str, UUID | None, UUID | None]] = set()
    batch_program_id: UUID | None = None
    projections: list[HttpObservationProjection] = []

    for row in rows:
        projection = http_observation_projection_from_row(row)
        if projection is None:
            continue
        projections.append(projection)
        batch_program_id = _batch_program_id(batch_program_id, projection.program_id)
        for fact in _http_observation_facts(projection, parser_version=parser_version):
            dedupe_key = (fact.identity_key, fact.source_artifact_id, fact.tool_run_id)
            if dedupe_key in seen_fact_keys:
                continue
            seen_fact_keys.add(dedupe_key)
            facts.append(fact)

    for fact in _response_difference_facts(projections):
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
    parameter_shapes = _parameter_shapes(projection)
    path_param_names = tuple(shape.name for shape in parameter_shapes if shape.location == "path")
    query_param_names = tuple(shape.name for shape in parameter_shapes if shape.location == "query")
    other_params = tuple(
        (shape.location, shape.name)
        for shape in parameter_shapes
        if shape.location not in {"path", "query"}
    )
    request_key = request_shape_key(
        endpoint_key=endpoint_key,
        method=projection.method,
        path_params=path_param_names,
        query_params=query_param_names,
        other_params=other_params,
    )
    response_key = _response_shape_key(projection)
    facts = [
        _node(projection, lineage, "Program", str(projection.program_id), {"program_id": str(projection.program_id)}),
        _node(projection, lineage, "Host", projection.hostname, {"hostname": projection.hostname}),
        _node(projection, lineage, "IP", projection.ip_address, {"address": projection.ip_address}),
        _service_node(projection, lineage, svc_key),
        _endpoint_node(projection, lineage, endpoint_key, svc_key),
        _request_shape_node(projection, lineage, request_key, endpoint_key, parameter_shapes),
        _response_shape_node(projection, lineage, response_key),
        _node(projection, lineage, "Artifact", str(projection.raw_artifact_id), {"artifact_id": str(projection.raw_artifact_id)}),
        _observation_node(projection, lineage, parser_version),
        _evidence_node(projection, lineage),
        _program_asset_edge(projection, lineage, "Host", projection.hostname),
        _program_asset_edge(projection, lineage, "IP", projection.ip_address),
        _program_asset_edge(projection, lineage, "Service", svc_key),
        _program_asset_edge(projection, lineage, "Endpoint", endpoint_key),
        _program_asset_edge(projection, lineage, "RequestShape", request_key),
        _program_asset_edge(projection, lineage, "ResponseShape", response_key),
        _edge(projection, lineage, "Host", projection.hostname, "RESOLVES_TO", "IP", projection.ip_address),
        _edge(projection, lineage, "Host", projection.hostname, "EXPOSES_SERVICE", "Service", svc_key, {"port": projection.port, "scheme": projection.scheme}),
        _edge(projection, lineage, "IP", projection.ip_address, "EXPOSES_SERVICE", "Service", svc_key, {"port": projection.port, "scheme": projection.scheme}),
        _edge(projection, lineage, "Service", svc_key, "HAS_ENDPOINT", "Endpoint", endpoint_key, {"method": projection.method, "status_code": projection.status_code}),
        _edge(projection, lineage, "Endpoint", endpoint_key, "HAS_REQUEST_SHAPE", "RequestShape", request_key, {"method": projection.method}),
        _yields_response_edge(projection, lineage, request_key, response_key),
        _edge(projection, lineage, "RequestShape", request_key, "SUPPORTED_BY", "Observation", str(projection.observation_id), {"confidence": 1.0}),
        _produced_observation_edge(projection, lineage, parser_version),
        _supports_evidence_edge(projection, lineage),
        _evidence_derived_from_edge(projection, lineage),
        _describes_edge(projection, lineage, "Host", projection.hostname),
        _describes_edge(projection, lineage, "IP", projection.ip_address),
        _describes_edge(projection, lineage, "Service", svc_key),
        _describes_edge(projection, lineage, "Endpoint", endpoint_key),
        _describes_edge(projection, lineage, "RequestShape", request_key),
        _describes_edge(projection, lineage, "ResponseShape", response_key),
    ]
    facts.extend(_parameter_facts(projection, lineage, endpoint_key, parameter_shapes))
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
    parameter_shapes: tuple[ParameterShape, ...],
) -> GraphNodeFact:
    grouped = _parameters_by_location(parameter_shapes)
    path_param_names = tuple(grouped.get("path", ()))
    query_param_names = tuple(grouped.get("query", ()))
    parameter_key_set = _parameter_key_set(grouped)
    request_body_param_names = tuple(grouped.get("body", ()))
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
            "parameter_key_set": parameter_key_set,
            "parameter_locations": sorted(grouped),
            "parameter_count": len(parameter_shapes),
            "request_body_param_keys": list(request_body_param_names),
            "request_body_shape_present": bool(request_body_param_names),
            "shape_fingerprint": request_key.rsplit("shape=", 1)[-1],
            "semantic_hash": stable_short_hash(projection.method, projection.normalized_path, ",".join(parameter_key_set)),
            "wire_hash": stable_short_hash(projection.method, projection.scheme, projection.hostname, projection.port, projection.normalized_path),
            "framing_hash": stable_short_hash(projection.method, bool(request_body_param_names), len(request_body_param_names)),
            "cache_key_candidate_hash": stable_short_hash(projection.method, projection.scheme, projection.hostname, projection.normalized_path, ",".join(query_param_names)),
            "parser_normalized_hash": stable_short_hash(projection.method, projection.normalized_path, ",".join(parameter_key_set)),
            "body_shape_hash": stable_short_hash("request_body_params", ",".join(request_body_param_names) or "-"),
            "response_shape_key": _response_shape_key(projection),
            "response_family": _response_family(projection),
            "display_label": _request_shape_display_label(projection, parameter_shapes),
        },
    )


def _response_shape_node(
    projection: HttpObservationProjection,
    lineage: dict[str, object],
    response_key: str,
) -> GraphNodeFact:
    family = _response_family(projection)
    body_size_bucket = _body_size_bucket(projection.body_size_bytes)
    header_key_hash = _header_key_hash(projection.response_header_names)
    return _node(
        projection,
        lineage,
        "ResponseShape",
        response_key,
        {
            "response_shape_key": response_key,
            "status_code": projection.status_code,
            "content_type": projection.content_type,
            "response_family": family,
            "response_header_keys": list(projection.response_header_names),
            "response_header_key_hash": header_key_hash,
            "body_sha256": projection.body_sha256,
            "body_size_bytes": projection.body_size_bytes,
            "body_size_bucket": body_size_bucket,
            "body_present": projection.body_sha256 is not None or bool(projection.body_size_bytes),
            "exact_body_hash": projection.body_sha256,
            "structural_hash": _response_structural_hash(projection),
            "schema_fingerprint": _response_schema_fingerprint(projection),
            "display_label": _response_shape_display_label(projection, family, body_size_bucket),
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


def _yields_response_edge(
    projection: HttpObservationProjection,
    lineage: dict[str, object],
    request_key: str,
    response_key: str,
) -> GraphEdgeFact:
    return _edge(
        projection,
        lineage,
        "RequestShape",
        request_key,
        "YIELDS_RESPONSE",
        "ResponseShape",
        response_key,
        {
            "count": 1,
            "status_code": projection.status_code,
            "status_histogram": [str(projection.status_code)] if projection.status_code is not None else [],
            "content_type": projection.content_type,
            "response_family": _response_family(projection),
            "body_size_bucket": _body_size_bucket(projection.body_size_bytes),
            "evidence_refs": [_evidence_key(projection)],
            "artifact_refs": [str(projection.raw_artifact_id)],
            "tool_run_refs": [str(projection.run_id)],
            "projection": "request_response_behavior",
            "semantics": "observed_response_shape_aggregate_not_raw_exchange",
        },
    )


def _response_difference_facts(projections: list[HttpObservationProjection]) -> list[GraphEdgeFact]:
    by_request: dict[str, list[HttpObservationProjection]] = {}
    for projection in projections:
        shapes = _parameter_shapes(projection)
        request_key = _request_key_for_projection(projection, shapes)
        by_request.setdefault(request_key, []).append(projection)

    facts: list[GraphEdgeFact] = []
    for observations in by_request.values():
        response_by_key: dict[str, HttpObservationProjection] = {}
        for projection in observations:
            response_by_key.setdefault(_response_shape_key(projection), projection)
        response_keys = sorted(response_by_key)
        if len(response_keys) < 2:
            continue
        for index, left_key in enumerate(response_keys):
            for right_key in response_keys[index + 1 :]:
                left = response_by_key[left_key]
                right = response_by_key[right_key]
                lineage = _lineage(left)
                facts.append(
                    _edge(
                        left,
                        lineage,
                        "ResponseShape",
                        left_key,
                        "DIFFERS_FROM",
                        "ResponseShape",
                        right_key,
                        _response_difference_properties(left, right),
                    )
                )
    return facts


def _parameter_facts(
    projection: HttpObservationProjection,
    lineage: dict[str, object],
    endpoint_key: str,
    shapes: tuple[ParameterShape, ...],
) -> list[GraphNodeFact | GraphEdgeFact]:
    facts: list[GraphNodeFact | GraphEdgeFact] = []
    for shape in shapes:
        facts.extend(_parameter_fact_triplet(projection, lineage, endpoint_key, shape))
    return facts


def _parameter_fact_triplet(
    projection: HttpObservationProjection,
    lineage: dict[str, object],
    endpoint_key: str,
    shape: ParameterShape,
) -> list[GraphNodeFact | GraphEdgeFact]:
    key = parameter_key(endpoint_key=endpoint_key, location=shape.location, name=shape.name)
    return [
        _node(
            projection,
            lineage,
            "Parameter",
            key,
            {
                "endpoint_location_name": key,
                "endpoint_key": endpoint_key,
                "location": shape.location,
                "name": shape.name,
                "param_type": shape.param_type,
                "display_label": f"{shape.location}:{shape.name} @ {_endpoint_display_label(projection)}",
                "is_array": shape.is_array,
                "reflected": shape.reflected,
                "shape_source": shape.source,
            },
        ),
        _program_asset_edge(projection, lineage, "Parameter", key),
        _edge(projection, lineage, "Endpoint", endpoint_key, "HAS_PARAM", "Parameter", key, {"location": shape.location}),
        _describes_edge(projection, lineage, "Parameter", key),
    ]


def _parameter_shapes(projection: HttpObservationProjection) -> tuple[ParameterShape, ...]:
    by_identity: dict[tuple[str, str], ParameterShape] = {}

    def add(shape: ParameterShape) -> None:
        key = (shape.location, shape.name)
        previous = by_identity.get(key)
        if previous is None or previous.source != "input_parameters":
            by_identity[key] = shape

    for parameter in projection.input_parameters:
        add(_parameter_from_projection(parameter))
    for name in _path_parameter_names(projection.normalized_path):
        add(ParameterShape(location="path", name=name, source="route_template"))
    for name, is_array in _query_parameter_items(projection.url):
        add(ParameterShape(location="query", name=name, is_array=is_array, source="url_query"))

    return tuple(sorted(by_identity.values(), key=lambda item: (item.location, item.name)))


def _request_key_for_projection(
    projection: HttpObservationProjection,
    parameter_shapes: tuple[ParameterShape, ...],
) -> str:
    svc_key = service_key(hostname=projection.hostname, port=projection.port, scheme=projection.scheme)
    endpoint_key = service_method_normalized_path_key(
        service_key=svc_key,
        method=projection.method,
        normalized_path=projection.normalized_path,
    )
    path_param_names = tuple(shape.name for shape in parameter_shapes if shape.location == "path")
    query_param_names = tuple(shape.name for shape in parameter_shapes if shape.location == "query")
    other_params = tuple(
        (shape.location, shape.name)
        for shape in parameter_shapes
        if shape.location not in {"path", "query"}
    )
    return request_shape_key(
        endpoint_key=endpoint_key,
        method=projection.method,
        path_params=path_param_names,
        query_params=query_param_names,
        other_params=other_params,
    )


def _response_shape_key(projection: HttpObservationProjection) -> str:
    return response_shape_key(
        program_id=projection.program_id,
        status_code=projection.status_code,
        content_type=projection.content_type,
        response_family=_response_family(projection),
        schema_fingerprint=_response_schema_fingerprint(projection),
        structural_hash=_response_structural_hash(projection),
        body_size_bucket=_body_size_bucket(projection.body_size_bytes),
        body_sha256=projection.body_sha256,
        header_key_hash=_header_key_hash(projection.response_header_names),
    )


def _response_family(projection: HttpObservationProjection) -> str:
    status = projection.status_code
    content_type = (projection.content_type or "").lower()
    if status is None:
        return "unknown_response"
    if status in {204, 205, 304}:
        return "empty_response"
    if status in {301, 302, 303, 307, 308}:
        return "redirect"
    if status in {401, 403}:
        return "auth_required"
    if status == 404:
        return "not_found"
    if status in {400, 409, 422}:
        return "validation_or_client_error"
    if status == 429:
        return "rate_limited"
    if 500 <= status <= 599:
        return "server_error"
    if 200 <= status <= 299 and "json" in content_type:
        return "success_json"
    if 200 <= status <= 299 and "html" in content_type:
        return "success_html"
    if 200 <= status <= 299:
        return "success_other"
    return "other_response"


def _response_structural_hash(projection: HttpObservationProjection) -> str:
    return stable_short_hash(
        projection.status_code if projection.status_code is not None else "-",
        projection.content_type or "-",
        _body_size_bucket(projection.body_size_bytes),
        _header_key_hash(projection.response_header_names),
    )


def _response_schema_fingerprint(projection: HttpObservationProjection) -> str:
    # Until a body schema extractor is available, keep this a safe class-level
    # fingerprint rather than a raw-body-derived property.
    return stable_short_hash(
        _response_family(projection),
        projection.content_type or "-",
        _header_key_hash(projection.response_header_names),
    )


def _response_difference_properties(
    left: HttpObservationProjection,
    right: HttpObservationProjection,
) -> dict[str, object]:
    return {
        "projection": "response_shape_delta",
        "oracle": "status_content_family_schema",
        "status_delta": left.status_code != right.status_code,
        "content_type_delta": (left.content_type or "") != (right.content_type or ""),
        "family_delta": _response_family(left) != _response_family(right),
        "schema_delta": _response_schema_fingerprint(left) != _response_schema_fingerprint(right),
        "body_size_bucket_delta": _body_size_bucket(left.body_size_bytes) != _body_size_bucket(right.body_size_bytes),
        "semantics": "advisory_response_shape_difference_not_finding_or_verdict",
    }


def _parameter_key_set(grouped: dict[str, tuple[str, ...]]) -> list[str]:
    values = [f"{location}:{name}" for location, names in grouped.items() for name in names]
    return sorted(set(values))


def _body_size_bucket(size: int | None) -> str:
    if size is None:
        return "unknown"
    if size <= 0:
        return "empty"
    if size < 512:
        return "tiny"
    if size < 4_096:
        return "small"
    if size < 65_536:
        return "medium"
    if size < 1_048_576:
        return "large"
    return "huge"


def _header_key_hash(header_names: tuple[str, ...]) -> str:
    return stable_short_hash(",".join(sorted(set(header_names))) or "-")


def _parameter_from_projection(parameter: InputParameterProjection) -> ParameterShape:
    return ParameterShape(
        location=parameter.location,
        name=parameter.name,
        param_type=parameter.param_type,
        reflected=parameter.reflected,
        is_array=parameter.is_array,
        source="input_parameters",
    )


def _parameters_by_location(shapes: tuple[ParameterShape, ...]) -> dict[str, tuple[str, ...]]:
    grouped: dict[str, list[str]] = {}
    for shape in shapes:
        grouped.setdefault(shape.location, []).append(shape.name)
    return {location: tuple(sorted(set(names))) for location, names in sorted(grouped.items())}


def _query_parameter_items(url: str | None) -> tuple[tuple[str, bool], ...]:
    if not url:
        return ()
    query = urlsplit(url).query
    if not query:
        return ()
    items = []
    for name, values in parse_qs(query, keep_blank_values=True).items():
        clean = name.strip()
        if clean:
            items.append((clean, len(values) > 1))
    return tuple(sorted(items))


def _path_parameter_names(normalized_path: str) -> tuple[str, ...]:
    names: set[str] = set()
    for pattern in (r"\{([^{}]+)\}", r"<([^<>]+)>", r"(?<=/):([A-Za-z_][A-Za-z0-9_]*)"):
        for match in re.finditer(pattern, normalized_path):
            name = match.group(1).strip()
            if name and name != "*":
                names.add(name)
    return tuple(sorted(names))


def _origin(projection: HttpObservationProjection) -> str:
    suffix = "" if (projection.scheme == "https" and projection.port == 443) or (projection.scheme == "http" and projection.port == 80) else f":{projection.port}"
    return f"{projection.scheme}://{projection.hostname}{suffix}"


def _endpoint_display_label(projection: HttpObservationProjection) -> str:
    return f"{projection.method} {projection.normalized_path} @ {projection.hostname}:{projection.port}"


def _request_shape_display_label(projection: HttpObservationProjection, parameter_shapes: tuple[ParameterShape, ...]) -> str:
    grouped = _parameters_by_location(parameter_shapes)
    query_param_names = grouped.get("query", ())
    suffix = f" ?{','.join(query_param_names)}" if query_param_names else ""
    body_suffix = " body" if grouped.get("body") else ""
    return f"{projection.method} {projection.normalized_path}{suffix}{body_suffix} @ {projection.hostname}:{projection.port}"


def _response_shape_display_label(projection: HttpObservationProjection, family: str, body_size_bucket: str) -> str:
    status = projection.status_code if projection.status_code is not None else "no-status"
    content = projection.content_type or "unknown-content"
    return f"{status} {family} {content} {body_size_bucket}"


def _evidence_key(projection: HttpObservationProjection) -> str:
    return f"http-observation:{projection.observation_id}"
