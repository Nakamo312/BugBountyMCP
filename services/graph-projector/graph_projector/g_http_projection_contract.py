from __future__ import annotations

from dataclasses import dataclass

from .projection_contracts import AlgorithmFamily, get_projection_contract


@dataclass(frozen=True, slots=True)
class GHttpNodeShape:
    node_type: str
    key_fields: tuple[str, ...]
    required_properties: tuple[str, ...]
    optional_properties: tuple[str, ...] = ()
    identity_only_fields: tuple[str, ...] = ()
    source_record_types: tuple[str, ...] = ()
    forbidden_properties: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GHttpEdgeShape:
    edge_type: str
    source_node_type: str
    target_node_type: str
    required_properties: tuple[str, ...]
    source_record_types: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GHttpStructuralSignalShape:
    signal_type: str
    algorithm_families: tuple[AlgorithmFamily, ...]
    required_lineage_fields: tuple[str, ...]
    evidence_ref_fields: tuple[str, ...]
    forbidden_payload_fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GHttpProjectionEventShape:
    projection_name: str
    contract_version: str
    event_type: str
    source_event_types: tuple[str, ...]
    source_record_types: tuple[str, ...]
    source_tables: tuple[str, ...]
    lineage_tables: tuple[str, ...]
    required_lineage_fields: tuple[str, ...]
    nodes: tuple[GHttpNodeShape, ...]
    edges: tuple[GHttpEdgeShape, ...]
    structural_signals: tuple[GHttpStructuralSignalShape, ...]
    forbidden_payload_fields: tuple[str, ...]
    status: str = "contract_only"


_G_HTTP_CONTRACT = get_projection_contract("G_http")

G_HTTP_SOURCE_RECORD_TYPES: tuple[str, ...] = (
    "HTTPObservationModel",
    "HTTPObservationHeaderModel",
    "EndpointModel",
    "ServiceModel",
    "HostModel",
    "IPAddressModel",
)

G_HTTP_SOURCE_TABLES: tuple[str, ...] = (
    "http_observations",
    "http_observation_headers",
    "endpoints",
    "services",
    "hosts",
    "ip_addresses",
)

G_HTTP_LINEAGE_TABLES: tuple[str, ...] = (
    "runs",
    "action_outcomes",
    "raw_artifacts",
)

G_HTTP_REQUIRED_LINEAGE_FIELDS: tuple[str, ...] = (
    "program_id",
    "projection_name",
    "projection_contract_version",
    "projection_snapshot_id",
    "http_observation_id",
    "endpoint_id",
    "service_id",
    "source_action_outcome_id",
    "run_id",
    "raw_artifact_id",
    "normalization_version",
)

G_HTTP_NODE_SHAPES: tuple[GHttpNodeShape, ...] = (
    GHttpNodeShape(
        node_type="endpoint",
        key_fields=("service_id", "method", "route_template"),
        required_properties=("method", "route_template", "endpoint_id"),
        optional_properties=("first_seen_at", "last_seen_at"),
        identity_only_fields=("service_id",),
        source_record_types=("HTTPObservationModel", "EndpointModel"),
        forbidden_properties=("raw_request_body", "raw_response_body", "cookie", "authorization"),
    ),
    GHttpNodeShape(
        node_type="route_template",
        key_fields=("host", "route_template"),
        required_properties=("host", "route_template", "normalization_version"),
        source_record_types=("EndpointModel",),
    ),
    GHttpNodeShape(
        node_type="method",
        key_fields=("method",),
        required_properties=("method",),
        source_record_types=("HTTPObservationModel",),
    ),
    GHttpNodeShape(
        node_type="param",
        key_fields=("endpoint_id", "location", "name"),
        required_properties=("location", "name"),
        optional_properties=("param_type", "is_array"),
        identity_only_fields=("endpoint_id",),
        source_record_types=("HTTPObservationModel",),
        forbidden_properties=("example_value", "raw_value", "secret_value"),
    ),
    GHttpNodeShape(
        node_type="body_schema",
        key_fields=("endpoint_id", "body_schema_hash"),
        required_properties=("body_schema_hash",),
        optional_properties=("schema_kind", "field_count"),
        identity_only_fields=("endpoint_id",),
        source_record_types=("HTTPObservationModel",),
        forbidden_properties=("raw_body", "body_preview"),
    ),
    GHttpNodeShape(
        node_type="response_shape",
        key_fields=("content_type", "status_class", "body_sha256"),
        required_properties=("content_type", "status_class", "body_sha256"),
        optional_properties=("body_size_bucket", "title_fingerprint"),
        source_record_types=("HTTPObservationModel",),
        forbidden_properties=("raw_response_body", "body_preview"),
    ),
    GHttpNodeShape(
        node_type="status_class",
        key_fields=("status_class",),
        required_properties=("status_class",),
        source_record_types=("HTTPObservationModel",),
    ),
    GHttpNodeShape(
        node_type="content_type",
        key_fields=("content_type",),
        required_properties=("content_type",),
        source_record_types=("HTTPObservationModel",),
    ),
    GHttpNodeShape(
        node_type="observed_action",
        key_fields=("run_id",),
        required_properties=("run_id", "source_tool"),
        optional_properties=("action_id", "job_id", "observed_at"),
        source_record_types=("HTTPObservationModel",),
    ),
)

G_HTTP_EDGE_SHAPES: tuple[GHttpEdgeShape, ...] = (
    GHttpEdgeShape("HAS_ROUTE_TEMPLATE", "endpoint", "route_template", ("projection_snapshot_id",), ("EndpointModel",)),
    GHttpEdgeShape("USES_METHOD", "endpoint", "method", ("projection_snapshot_id",), ("HTTPObservationModel",)),
    GHttpEdgeShape("HAS_PARAM", "endpoint", "param", ("location", "projection_snapshot_id"), ("HTTPObservationModel",)),
    GHttpEdgeShape("HAS_BODY_SCHEMA", "endpoint", "body_schema", ("projection_snapshot_id",), ("HTTPObservationModel",)),
    GHttpEdgeShape("RETURNS_RESPONSE_SHAPE", "endpoint", "response_shape", ("projection_snapshot_id",), ("HTTPObservationModel",)),
    GHttpEdgeShape("RETURNS_STATUS_CLASS", "endpoint", "status_class", ("projection_snapshot_id",), ("HTTPObservationModel",)),
    GHttpEdgeShape("RETURNS_CONTENT_TYPE", "endpoint", "content_type", ("projection_snapshot_id",), ("HTTPObservationModel",)),
    GHttpEdgeShape("OBSERVED_BY_ACTION", "endpoint", "observed_action", ("run_id", "projection_snapshot_id"), ("HTTPObservationModel",)),
)

G_HTTP_SIGNAL_SHAPES: tuple[GHttpStructuralSignalShape, ...] = (
    GHttpStructuralSignalShape(
        signal_type="HttpEndpointNeighborhoodSignal",
        algorithm_families=(AlgorithmFamily.DEGREE, AlgorithmFamily.JACCARD_SIMILARITY),
        required_lineage_fields=G_HTTP_REQUIRED_LINEAGE_FIELDS,
        evidence_ref_fields=("http_observation_ids", "endpoint_ids", "projection_snapshot_id"),
        forbidden_payload_fields=("raw_headers", "raw_request_body", "raw_response_body", "cookies", "authorization"),
    ),
    GHttpStructuralSignalShape(
        signal_type="HttpCoverageGapSignal",
        algorithm_families=(AlgorithmFamily.COVERAGE_SUMMARY,),
        required_lineage_fields=G_HTTP_REQUIRED_LINEAGE_FIELDS,
        evidence_ref_fields=("http_observation_ids", "endpoint_ids", "coverage_window_id"),
        forbidden_payload_fields=("raw_headers", "cookies", "authorization"),
    ),
    GHttpStructuralSignalShape(
        signal_type="HttpDriftSignal",
        algorithm_families=(AlgorithmFamily.DRIFT_SUMMARY,),
        required_lineage_fields=G_HTTP_REQUIRED_LINEAGE_FIELDS,
        evidence_ref_fields=("previous_projection_snapshot_id", "current_projection_snapshot_id", "http_observation_ids"),
        forbidden_payload_fields=("raw_request_body", "raw_response_body", "body_preview"),
    ),
    GHttpStructuralSignalShape(
        signal_type="HttpMissingRelationCandidateSignal",
        algorithm_families=(AlgorithmFamily.JACCARD_SIMILARITY, AlgorithmFamily.COVERAGE_SUMMARY),
        required_lineage_fields=G_HTTP_REQUIRED_LINEAGE_FIELDS,
        evidence_ref_fields=("endpoint_ids", "param_ids", "projection_snapshot_id"),
        forbidden_payload_fields=("example_value", "raw_value", "secret_value"),
    ),
)

G_HTTP_PROJECTION_EVENT_SHAPE = GHttpProjectionEventShape(
    projection_name="G_http",
    contract_version=_G_HTTP_CONTRACT.contract_version,
    event_type="G_http_projection_snapshot_ready",
    source_event_types=("http_observations_ready",),
    source_record_types=G_HTTP_SOURCE_RECORD_TYPES,
    source_tables=G_HTTP_SOURCE_TABLES,
    lineage_tables=G_HTTP_LINEAGE_TABLES,
    required_lineage_fields=G_HTTP_REQUIRED_LINEAGE_FIELDS,
    nodes=G_HTTP_NODE_SHAPES,
    edges=G_HTTP_EDGE_SHAPES,
    structural_signals=G_HTTP_SIGNAL_SHAPES,
    forbidden_payload_fields=(
        "raw_headers",
        "raw_request_body",
        "raw_response_body",
        "body_preview",
        "cookies",
        "authorization",
        "token",
        "secret",
    ),
)




def validate_g_http_projection_event_shape(
    event_shape: GHttpProjectionEventShape = G_HTTP_PROJECTION_EVENT_SHAPE,
) -> None:
    if event_shape.projection_name != _G_HTTP_CONTRACT.name:
        raise ValueError("G_http event shape projection_name must match the projection contract")
    if event_shape.contract_version != _G_HTTP_CONTRACT.contract_version:
        raise ValueError("G_http event shape contract_version must match the projection contract")
    if event_shape.event_type != "G_http_projection_snapshot_ready":
        raise ValueError("G_http event shape must describe the ready projection snapshot output")
    if event_shape.status != "contract_only":
        raise ValueError("G_http event shape must remain contract_only until runtime projection exists")

    source_records = set(event_shape.source_record_types)
    lineage_fields = set(event_shape.required_lineage_fields)
    forbidden_payloads = set(event_shape.forbidden_payload_fields)
    forbidden_url_fields = {"url_sample", "raw_url", "full_url", "query", "fragment"}

    for node in event_shape.nodes:
        unknown_sources = set(node.source_record_types) - source_records
        if unknown_sources:
            raise ValueError(f"node {node.node_type} references non-source records: {sorted(unknown_sources)}")
        key_fields = set(node.key_fields)
        available_identity_fields = set(node.required_properties) | lineage_fields | set(node.identity_only_fields)
        missing_key_fields = key_fields - available_identity_fields
        if missing_key_fields:
            raise ValueError(
                f"node {node.node_type} key fields are not required, lineage, or identity-only: "
                f"{sorted(missing_key_fields)}"
            )
        leaked_url_fields = forbidden_url_fields & (set(node.required_properties) | set(node.optional_properties))
        if leaked_url_fields:
            raise ValueError(f"node {node.node_type} exposes raw URL/sample fields: {sorted(leaked_url_fields)}")
        forbidden_overlap = forbidden_payloads & (set(node.required_properties) | set(node.optional_properties))
        if forbidden_overlap:
            raise ValueError(f"node {node.node_type} exposes forbidden payload fields: {sorted(forbidden_overlap)}")

    node_types = {node.node_type for node in event_shape.nodes}
    for edge in event_shape.edges:
        unknown_sources = set(edge.source_record_types) - source_records
        if unknown_sources:
            raise ValueError(f"edge {edge.edge_type} references non-source records: {sorted(unknown_sources)}")
        if edge.source_node_type not in node_types or edge.target_node_type not in node_types:
            raise ValueError(f"edge {edge.edge_type} references unknown node types")

    minimal_lineage = {
        "program_id",
        "projection_name",
        "projection_contract_version",
        "projection_snapshot_id",
        "http_observation_id",
        "endpoint_id",
        "service_id",
        "normalization_version",
    }
    missing_lineage = minimal_lineage - lineage_fields
    if missing_lineage:
        raise ValueError(f"G_http event shape missing minimal lineage fields: {sorted(missing_lineage)}")

    for signal in event_shape.structural_signals:
        signal_lineage = set(signal.required_lineage_fields)
        if not lineage_fields.issubset(signal_lineage):
            missing = lineage_fields - signal_lineage
            raise ValueError(f"signal {signal.signal_type} does not preserve event lineage: {sorted(missing)}")


validate_g_http_projection_event_shape()


def g_http_node_types() -> tuple[str, ...]:
    return tuple(node.node_type for node in G_HTTP_NODE_SHAPES)


def g_http_edge_types() -> tuple[str, ...]:
    return tuple(edge.edge_type for edge in G_HTTP_EDGE_SHAPES)


def g_http_signal_types() -> tuple[str, ...]:
    return tuple(signal.signal_type for signal in G_HTTP_SIGNAL_SHAPES)
