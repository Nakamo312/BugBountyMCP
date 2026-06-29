from __future__ import annotations

from dataclasses import dataclass

from .g_http_projection_contract import g_http_edge_types, g_http_node_types
from .projection_contracts import AlgorithmFamily, get_projection_contract


@dataclass(frozen=True, slots=True)
class SourceProjectionRef:
    projection_name: str
    contract_version: str


@dataclass(frozen=True, slots=True)
class EndpointParamNodeShape:
    node_type: str
    key_fields: tuple[str, ...]
    required_properties: tuple[str, ...]
    optional_properties: tuple[str, ...] = ()
    identity_only_fields: tuple[str, ...] = ()
    source_projection_node_types: tuple[str, ...] = ()
    forbidden_properties: tuple[str, ...] = ()
    key_scope: str = "projection_snapshot"


@dataclass(frozen=True, slots=True)
class EndpointParamEdgeShape:
    edge_type: str
    source_node_type: str
    target_node_type: str
    required_properties: tuple[str, ...]
    source_projection_edge_types: tuple[str, ...]
    required_lineage_fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EndpointParamStructuralSignalShape:
    signal_type: str
    algorithm_families: tuple[AlgorithmFamily, ...]
    required_lineage_fields: tuple[str, ...]
    evidence_ref_fields: tuple[str, ...]
    forbidden_payload_fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EndpointParamProjectionEventShape:
    projection_name: str
    contract_version: str
    event_type: str
    source_event_types: tuple[str, ...]
    source_projections: tuple[SourceProjectionRef, ...]
    snapshot_lineage_fields: tuple[str, ...]
    nodes: tuple[EndpointParamNodeShape, ...]
    edges: tuple[EndpointParamEdgeShape, ...]
    structural_signals: tuple[EndpointParamStructuralSignalShape, ...]
    forbidden_payload_fields: tuple[str, ...]
    status: str = "contract_only"


_ENDPOINT_PARAM_CONTRACT = get_projection_contract("G_bipartite_endpoint_param")
_G_HTTP_CONTRACT = get_projection_contract("G_http")

ENDPOINT_PARAM_SOURCE_PROJECTIONS: tuple[SourceProjectionRef, ...] = (
    SourceProjectionRef("G_http", _G_HTTP_CONTRACT.contract_version),
)

ENDPOINT_PARAM_SNAPSHOT_LINEAGE_FIELDS: tuple[str, ...] = (
    "program_id",
    "projection_name",
    "projection_contract_version",
    "projection_snapshot_id",
    "source_projection_name",
    "source_projection_contract_version",
    "source_projection_snapshot_id",
    "normalization_version",
)

ENDPOINT_PARAM_EDGE_LINEAGE_FIELDS: tuple[str, ...] = (
    "endpoint_id",
    "param_id",
    "source_projection_snapshot_id",
)

ENDPOINT_PARAM_NODE_SHAPES: tuple[EndpointParamNodeShape, ...] = (
    EndpointParamNodeShape(
        node_type="endpoint",
        key_fields=("endpoint_id",),
        required_properties=("endpoint_id", "method", "route_template"),
        optional_properties=("first_seen_at", "last_seen_at"),
        identity_only_fields=("service_id",),
        source_projection_node_types=("endpoint",),
        forbidden_properties=("raw_url", "url_sample", "query", "fragment", "raw_request_body"),
        key_scope="source_projection_snapshot",
    ),
    EndpointParamNodeShape(
        node_type="param",
        key_fields=("location", "name", "normalization_version"),
        required_properties=("location", "name", "normalization_version"),
        optional_properties=("param_type", "is_array", "sensitivity_flag"),
        source_projection_node_types=("param",),
        forbidden_properties=("example_value", "raw_value", "secret_value", "query_value"),
        key_scope="projection_snapshot",
    ),
)

ENDPOINT_PARAM_EDGE_SHAPES: tuple[EndpointParamEdgeShape, ...] = (
    EndpointParamEdgeShape(
        edge_type="HAS_PARAM",
        source_node_type="endpoint",
        target_node_type="param",
        required_properties=(
            "projection_snapshot_id",
            "source_projection_snapshot_id",
            "observed_count",
        ),
        source_projection_edge_types=("HAS_PARAM",),
        required_lineage_fields=ENDPOINT_PARAM_EDGE_LINEAGE_FIELDS,
    ),
)

ENDPOINT_PARAM_SIGNAL_SHAPES: tuple[EndpointParamStructuralSignalShape, ...] = (
    EndpointParamStructuralSignalShape(
        signal_type="EndpointParamSimilaritySignal",
        algorithm_families=(AlgorithmFamily.JACCARD_SIMILARITY,),
        required_lineage_fields=ENDPOINT_PARAM_SNAPSHOT_LINEAGE_FIELDS,
        evidence_ref_fields=("endpoint_ids", "shared_param_ids", "source_projection_snapshot_id"),
        forbidden_payload_fields=("example_value", "raw_value", "secret_value", "raw_url", "query_value"),
    ),
    EndpointParamStructuralSignalShape(
        signal_type="ParamCentralitySignal",
        algorithm_families=(AlgorithmFamily.DEGREE, AlgorithmFamily.CENTRALITY),
        required_lineage_fields=ENDPOINT_PARAM_SNAPSHOT_LINEAGE_FIELDS,
        evidence_ref_fields=("param_id", "endpoint_ids", "source_projection_snapshot_id"),
        forbidden_payload_fields=("example_value", "raw_value", "secret_value", "query_value"),
    ),
    EndpointParamStructuralSignalShape(
        signal_type="MissingEndpointParamCandidateSignal",
        algorithm_families=(AlgorithmFamily.BIPARTITE_LINK_PREDICTION_BASELINE,),
        required_lineage_fields=ENDPOINT_PARAM_SNAPSHOT_LINEAGE_FIELDS,
        evidence_ref_fields=(
            "candidate_endpoint_id",
            "candidate_param_id",
            "neighbor_endpoint_ids",
            "source_projection_snapshot_id",
        ),
        forbidden_payload_fields=("example_value", "raw_value", "secret_value", "raw_url", "query_value"),
    ),
)

ENDPOINT_PARAM_PROJECTION_EVENT_SHAPE = EndpointParamProjectionEventShape(
    projection_name="G_bipartite_endpoint_param",
    contract_version=_ENDPOINT_PARAM_CONTRACT.contract_version,
    event_type="G_bipartite_endpoint_param_projection_snapshot_ready",
    source_event_types=("G_http_projection_snapshot_ready",),
    source_projections=ENDPOINT_PARAM_SOURCE_PROJECTIONS,
    snapshot_lineage_fields=ENDPOINT_PARAM_SNAPSHOT_LINEAGE_FIELDS,
    nodes=ENDPOINT_PARAM_NODE_SHAPES,
    edges=ENDPOINT_PARAM_EDGE_SHAPES,
    structural_signals=ENDPOINT_PARAM_SIGNAL_SHAPES,
    forbidden_payload_fields=(
        "example_value",
        "raw_value",
        "secret_value",
        "query_value",
        "raw_url",
        "url_sample",
        "query",
        "fragment",
        "authorization",
        "cookies",
    ),
)


def validate_endpoint_param_projection_event_shape(
    event_shape: EndpointParamProjectionEventShape = ENDPOINT_PARAM_PROJECTION_EVENT_SHAPE,
) -> None:
    if event_shape.projection_name != _ENDPOINT_PARAM_CONTRACT.name:
        raise ValueError("endpoint-param event shape projection_name must match projection contract")
    if event_shape.contract_version != _ENDPOINT_PARAM_CONTRACT.contract_version:
        raise ValueError("endpoint-param event shape contract_version must match projection contract")
    if event_shape.event_type != "G_bipartite_endpoint_param_projection_snapshot_ready":
        raise ValueError("endpoint-param event shape must describe the ready projection snapshot output")
    if event_shape.status != "contract_only":
        raise ValueError("endpoint-param event shape must remain contract_only until runtime projection exists")

    expected_sources = tuple(
        SourceProjectionRef(source_name, get_projection_contract(source_name).contract_version)
        for source_name in _ENDPOINT_PARAM_CONTRACT.source_projections
    )
    if event_shape.source_projections != expected_sources:
        raise ValueError("endpoint-param source projections must match the projection contract dependencies")

    snapshot_lineage_fields = set(event_shape.snapshot_lineage_fields)
    forbidden_payloads = set(event_shape.forbidden_payload_fields)
    contract_node_types = set(_ENDPOINT_PARAM_CONTRACT.node_types)
    contract_edge_types = set(_ENDPOINT_PARAM_CONTRACT.edge_types)
    source_projection_names = {source.projection_name for source in event_shape.source_projections}
    if source_projection_names != set(_ENDPOINT_PARAM_CONTRACT.source_projections):
        raise ValueError("endpoint-param source projection names drifted from the projection contract")

    minimal_snapshot_lineage = set(ENDPOINT_PARAM_SNAPSHOT_LINEAGE_FIELDS)
    missing_snapshot_lineage = minimal_snapshot_lineage - snapshot_lineage_fields
    if missing_snapshot_lineage:
        raise ValueError(
            f"endpoint-param event shape missing snapshot lineage fields: {sorted(missing_snapshot_lineage)}"
        )
    relation_lineage = {"endpoint_id", "param_id"}
    if snapshot_lineage_fields & relation_lineage:
        raise ValueError("endpoint_id and param_id belong to edge or signal evidence, not snapshot lineage")

    source_http_node_types = set(g_http_node_types())
    source_http_edge_types = set(g_http_edge_types())
    allowed_key_scopes = {"projection_snapshot", "source_projection_snapshot"}

    for node in event_shape.nodes:
        if node.node_type not in contract_node_types:
            raise ValueError(f"node {node.node_type} is not allowed by G_bipartite_endpoint_param")
        if node.key_scope not in allowed_key_scopes:
            raise ValueError(f"node {node.node_type} has unsupported key scope: {node.key_scope}")
        if not node.source_projection_node_types:
            raise ValueError(f"node {node.node_type} must name source projection node types")
        unknown_source_node_types = set(node.source_projection_node_types) - source_http_node_types
        if unknown_source_node_types:
            raise ValueError(
                f"node {node.node_type} references unknown G_http node types: "
                f"{sorted(unknown_source_node_types)}"
            )
        available_identity_fields = (
            set(node.required_properties) | snapshot_lineage_fields | set(node.identity_only_fields)
        )
        missing_key_fields = set(node.key_fields) - available_identity_fields
        if missing_key_fields:
            raise ValueError(
                f"node {node.node_type} key fields are not required, lineage, or identity-only: "
                f"{sorted(missing_key_fields)}"
            )
        emitted_properties = set(node.required_properties) | set(node.optional_properties)
        forbidden_overlap = (forbidden_payloads | set(node.forbidden_properties)) & emitted_properties
        if forbidden_overlap:
            raise ValueError(f"node {node.node_type} exposes forbidden payload fields: {sorted(forbidden_overlap)}")

    node_types = {node.node_type for node in event_shape.nodes}
    for edge in event_shape.edges:
        if edge.edge_type not in contract_edge_types:
            raise ValueError(f"edge {edge.edge_type} is not allowed by G_bipartite_endpoint_param")
        if edge.source_node_type not in node_types or edge.target_node_type not in node_types:
            raise ValueError(f"edge {edge.edge_type} references unknown node types")
        if not edge.source_projection_edge_types:
            raise ValueError(f"edge {edge.edge_type} must name source projection edge types")
        unknown_source_edge_types = set(edge.source_projection_edge_types) - source_http_edge_types
        if unknown_source_edge_types:
            raise ValueError(
                f"edge {edge.edge_type} references unknown G_http edge types: "
                f"{sorted(unknown_source_edge_types)}"
            )
        missing_edge_lineage = set(ENDPOINT_PARAM_EDGE_LINEAGE_FIELDS) - set(edge.required_lineage_fields)
        if missing_edge_lineage:
            raise ValueError(f"edge {edge.edge_type} missing relation lineage fields: {sorted(missing_edge_lineage)}")
        forbidden_overlap = forbidden_payloads & (set(edge.required_properties) | set(edge.required_lineage_fields))
        if forbidden_overlap:
            raise ValueError(f"edge {edge.edge_type} exposes forbidden payload fields: {sorted(forbidden_overlap)}")

    contract_signal_map = {
        signal.signal_type: set(signal.algorithm_families)
        for signal in _ENDPOINT_PARAM_CONTRACT.output_signal_families
    }
    for signal in event_shape.structural_signals:
        if signal.signal_type not in contract_signal_map:
            raise ValueError(f"signal {signal.signal_type} is not allowed by G_bipartite_endpoint_param")
        if set(signal.algorithm_families) != contract_signal_map[signal.signal_type]:
            raise ValueError(f"signal {signal.signal_type} algorithm family mapping drifted from the contract")
        if not snapshot_lineage_fields.issubset(set(signal.required_lineage_fields)):
            missing = snapshot_lineage_fields - set(signal.required_lineage_fields)
            raise ValueError(f"signal {signal.signal_type} does not preserve snapshot lineage: {sorted(missing)}")
        forbidden_overlap = (forbidden_payloads | set(signal.forbidden_payload_fields)) & set(signal.evidence_ref_fields)
        if forbidden_overlap:
            raise ValueError(f"signal {signal.signal_type} uses forbidden evidence payload fields: {sorted(forbidden_overlap)}")


validate_endpoint_param_projection_event_shape()


def endpoint_param_node_types() -> tuple[str, ...]:
    return tuple(node.node_type for node in ENDPOINT_PARAM_NODE_SHAPES)


def endpoint_param_edge_types() -> tuple[str, ...]:
    return tuple(edge.edge_type for edge in ENDPOINT_PARAM_EDGE_SHAPES)


def endpoint_param_signal_types() -> tuple[str, ...]:
    return tuple(signal.signal_type for signal in ENDPOINT_PARAM_SIGNAL_SHAPES)
