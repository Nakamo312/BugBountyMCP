from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path("services/graph-projector").resolve()))

from graph_projector.g_bipartite_endpoint_param_contract import (  # noqa: E402
    ENDPOINT_PARAM_EDGE_LINEAGE_FIELDS,
    ENDPOINT_PARAM_EDGE_SHAPES,
    ENDPOINT_PARAM_NODE_SHAPES,
    ENDPOINT_PARAM_PROJECTION_EVENT_SHAPE,
    ENDPOINT_PARAM_SIGNAL_SHAPES,
    ENDPOINT_PARAM_SNAPSHOT_LINEAGE_FIELDS,
    ENDPOINT_PARAM_SOURCE_PROJECTIONS,
    EndpointParamEdgeShape,
    EndpointParamNodeShape,
    EndpointParamProjectionEventShape,
    SourceProjectionRef,
    endpoint_param_edge_types,
    endpoint_param_node_types,
    endpoint_param_signal_types,
    validate_endpoint_param_projection_event_shape,
)
from graph_projector.g_http_projection_contract import g_http_edge_types, g_http_node_types  # noqa: E402
from graph_projector.projection_contracts import AlgorithmFamily, get_projection_contract  # noqa: E402


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_endpoint_param_projection_shape_references_versioned_projection_contract() -> None:
    contract = get_projection_contract("G_bipartite_endpoint_param")
    event_shape = ENDPOINT_PARAM_PROJECTION_EVENT_SHAPE

    assert event_shape.status == "contract_only"
    assert event_shape.projection_name == contract.name
    assert event_shape.contract_version == contract.contract_version
    assert event_shape.event_type == "G_bipartite_endpoint_param_projection_snapshot_ready"
    assert event_shape.source_event_types == ("G_http_projection_snapshot_ready",)
    assert ENDPOINT_PARAM_SOURCE_PROJECTIONS == (SourceProjectionRef("G_http", "v1"),)
    assert set(endpoint_param_node_types()) == set(contract.node_types)
    assert set(endpoint_param_edge_types()) == set(contract.edge_types)
    assert set(endpoint_param_signal_types()) == set(contract.output_signals)


def test_endpoint_param_projection_shape_defines_minimal_bipartite_space() -> None:
    assert endpoint_param_node_types() == ("endpoint", "param")
    assert endpoint_param_edge_types() == ("HAS_PARAM",)
    assert endpoint_param_signal_types() == (
        "EndpointParamSimilaritySignal",
        "ParamCentralitySignal",
        "MissingEndpointParamCandidateSignal",
    )
    assert {node.node_type for node in ENDPOINT_PARAM_NODE_SHAPES} == {"endpoint", "param"}
    assert {edge.edge_type for edge in ENDPOINT_PARAM_EDGE_SHAPES} == {"HAS_PARAM"}


def test_endpoint_param_projection_nodes_and_edges_are_sourced_from_g_http_shapes() -> None:
    http_nodes = set(g_http_node_types())
    http_edges = set(g_http_edge_types())

    for node in ENDPOINT_PARAM_NODE_SHAPES:
        assert set(node.source_projection_node_types) <= http_nodes
    for edge in ENDPOINT_PARAM_EDGE_SHAPES:
        assert set(edge.source_projection_edge_types) <= http_edges


def test_endpoint_param_projection_depends_on_g_http_without_runtime_projection_logic() -> None:
    contract = get_projection_contract("G_bipartite_endpoint_param")
    assert contract.source_projections == ("G_http",)
    assert ENDPOINT_PARAM_PROJECTION_EVENT_SHAPE.source_projections == (SourceProjectionRef("G_http", "v1"),)

    source = _read("services/graph-projector/graph_projector/g_bipartite_endpoint_param_contract.py")
    assert "GraphDatabase" not in source
    assert "gds." not in source
    assert "session.run" not in source
    assert "CREATE" not in source
    assert "MERGE" not in source
    assert "ActionService" not in source


def test_endpoint_param_projection_snapshot_lineage_does_not_claim_single_relation_ids() -> None:
    snapshot_lineage = set(ENDPOINT_PARAM_PROJECTION_EVENT_SHAPE.snapshot_lineage_fields)
    assert set(ENDPOINT_PARAM_SNAPSHOT_LINEAGE_FIELDS) <= snapshot_lineage
    assert "endpoint_id" not in snapshot_lineage
    assert "param_id" not in snapshot_lineage

    edge = ENDPOINT_PARAM_EDGE_SHAPES[0]
    assert set(ENDPOINT_PARAM_EDGE_LINEAGE_FIELDS) <= set(edge.required_lineage_fields)
    assert {"endpoint_id", "param_id"} <= set(edge.required_lineage_fields)

    signals = {signal.signal_type: signal for signal in ENDPOINT_PARAM_SIGNAL_SHAPES}
    assert signals["EndpointParamSimilaritySignal"].evidence_ref_fields == (
        "endpoint_ids",
        "shared_param_ids",
        "source_projection_snapshot_id",
    )
    assert "param_id" in signals["ParamCentralitySignal"].evidence_ref_fields
    assert "candidate_endpoint_id" in signals["MissingEndpointParamCandidateSignal"].evidence_ref_fields
    assert "candidate_param_id" in signals["MissingEndpointParamCandidateSignal"].evidence_ref_fields


def test_endpoint_param_projection_shape_forbids_raw_parameter_values_and_urls() -> None:
    forbidden = set(ENDPOINT_PARAM_PROJECTION_EVENT_SHAPE.forbidden_payload_fields)
    for raw_field in ("example_value", "raw_value", "secret_value", "query_value", "raw_url", "url_sample"):
        assert raw_field in forbidden

    for node in ENDPOINT_PARAM_NODE_SHAPES:
        emitted_properties = set(node.required_properties) | set(node.optional_properties)
        assert emitted_properties.isdisjoint(forbidden | set(node.forbidden_properties))
    for signal in ENDPOINT_PARAM_SIGNAL_SHAPES:
        assert set(signal.evidence_ref_fields).isdisjoint(forbidden | set(signal.forbidden_payload_fields))


def test_endpoint_param_projection_shape_keeps_key_fields_available_and_scoped() -> None:
    snapshot_lineage_fields = set(ENDPOINT_PARAM_PROJECTION_EVENT_SHAPE.snapshot_lineage_fields)
    allowed_scopes = {"projection_snapshot", "source_projection_snapshot"}
    for node in ENDPOINT_PARAM_NODE_SHAPES:
        assert node.key_scope in allowed_scopes
        available_identity_fields = set(node.required_properties) | snapshot_lineage_fields | set(node.identity_only_fields)
        assert set(node.key_fields) <= available_identity_fields

    param = next(node for node in ENDPOINT_PARAM_NODE_SHAPES if node.node_type == "param")
    assert param.key_scope == "projection_snapshot"


def test_endpoint_param_signal_shapes_map_to_allowed_algorithm_families() -> None:
    contract = get_projection_contract("G_bipartite_endpoint_param")
    contract_signal_map = {
        signal.signal_type: set(signal.algorithm_families)
        for signal in contract.output_signal_families
    }

    for signal in ENDPOINT_PARAM_SIGNAL_SHAPES:
        assert set(signal.algorithm_families) == contract_signal_map[signal.signal_type]
        assert set(signal.algorithm_families).issubset(set(contract.algorithm_families))
        assert set(ENDPOINT_PARAM_SNAPSHOT_LINEAGE_FIELDS) <= set(signal.required_lineage_fields)
        assert "source_projection_snapshot_id" in signal.evidence_ref_fields

    assert contract_signal_map["EndpointParamSimilaritySignal"] == {AlgorithmFamily.JACCARD_SIMILARITY}
    assert contract_signal_map["ParamCentralitySignal"] == {AlgorithmFamily.DEGREE, AlgorithmFamily.CENTRALITY}
    assert contract_signal_map["MissingEndpointParamCandidateSignal"] == {
        AlgorithmFamily.BIPARTITE_LINK_PREDICTION_BASELINE
    }


def test_endpoint_param_projection_shape_validation_rejects_dependency_and_key_drift() -> None:
    valid = ENDPOINT_PARAM_PROJECTION_EVENT_SHAPE

    wrong_dependency = EndpointParamProjectionEventShape(
        projection_name=valid.projection_name,
        contract_version=valid.contract_version,
        event_type=valid.event_type,
        source_event_types=valid.source_event_types,
        source_projections=(SourceProjectionRef("G_asset", "v1"),),
        snapshot_lineage_fields=valid.snapshot_lineage_fields,
        nodes=valid.nodes,
        edges=valid.edges,
        structural_signals=valid.structural_signals,
        forbidden_payload_fields=valid.forbidden_payload_fields,
    )
    try:
        validate_endpoint_param_projection_event_shape(wrong_dependency)
    except ValueError as exc:
        assert "source projections" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("wrong source projection should be rejected")

    bad_key_node = EndpointParamNodeShape(
        node_type="param",
        key_fields=("missing_key",),
        required_properties=("name",),
        source_projection_node_types=("param",),
    )
    bad_key = EndpointParamProjectionEventShape(
        projection_name=valid.projection_name,
        contract_version=valid.contract_version,
        event_type=valid.event_type,
        source_event_types=valid.source_event_types,
        source_projections=valid.source_projections,
        snapshot_lineage_fields=valid.snapshot_lineage_fields,
        nodes=valid.nodes + (bad_key_node,),
        edges=valid.edges,
        structural_signals=valid.structural_signals,
        forbidden_payload_fields=valid.forbidden_payload_fields,
    )
    try:
        validate_endpoint_param_projection_event_shape(bad_key)
    except ValueError as exc:
        assert "key fields" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("missing node key field should be rejected")


def test_endpoint_param_projection_shape_validation_rejects_snapshot_relation_lineage_and_bad_event_type() -> None:
    valid = ENDPOINT_PARAM_PROJECTION_EVENT_SHAPE
    relation_lineage_on_snapshot = EndpointParamProjectionEventShape(
        projection_name=valid.projection_name,
        contract_version=valid.contract_version,
        event_type=valid.event_type,
        source_event_types=valid.source_event_types,
        source_projections=valid.source_projections,
        snapshot_lineage_fields=valid.snapshot_lineage_fields + ("endpoint_id",),
        nodes=valid.nodes,
        edges=valid.edges,
        structural_signals=valid.structural_signals,
        forbidden_payload_fields=valid.forbidden_payload_fields,
    )
    try:
        validate_endpoint_param_projection_event_shape(relation_lineage_on_snapshot)
    except ValueError as exc:
        assert "snapshot lineage" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("snapshot-level endpoint_id should be rejected")

    request_named_shape = EndpointParamProjectionEventShape(
        projection_name=valid.projection_name,
        contract_version=valid.contract_version,
        event_type="G_bipartite_endpoint_param_projection_snapshot_requested",
        source_event_types=valid.source_event_types,
        source_projections=valid.source_projections,
        snapshot_lineage_fields=valid.snapshot_lineage_fields,
        nodes=valid.nodes,
        edges=valid.edges,
        structural_signals=valid.structural_signals,
        forbidden_payload_fields=valid.forbidden_payload_fields,
    )
    try:
        validate_endpoint_param_projection_event_shape(request_named_shape)
    except ValueError as exc:
        assert "ready projection snapshot" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("request event type should be rejected for output shape")


def test_endpoint_param_projection_shape_validation_rejects_node_level_forbidden_properties() -> None:
    valid = ENDPOINT_PARAM_PROJECTION_EVENT_SHAPE
    bad_node = EndpointParamNodeShape(
        node_type="endpoint",
        key_fields=("endpoint_id",),
        required_properties=("endpoint_id", "url_sample"),
        source_projection_node_types=("endpoint",),
        forbidden_properties=("url_sample",),
    )
    bad_shape = EndpointParamProjectionEventShape(
        projection_name=valid.projection_name,
        contract_version=valid.contract_version,
        event_type=valid.event_type,
        source_event_types=valid.source_event_types,
        source_projections=valid.source_projections,
        snapshot_lineage_fields=valid.snapshot_lineage_fields,
        nodes=valid.nodes + (bad_node,),
        edges=valid.edges,
        structural_signals=valid.structural_signals,
        forbidden_payload_fields=valid.forbidden_payload_fields,
    )
    try:
        validate_endpoint_param_projection_event_shape(bad_shape)
    except ValueError as exc:
        assert "forbidden payload fields" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("node-level forbidden property should be rejected")


def test_endpoint_param_projection_contract_is_linked_from_docs() -> None:
    docs = _read("docs/architecture/bipartite-endpoint-param-contract.md")
    typed_doc = _read("docs/architecture/typed-graph-projections.md")
    backlog = _read("docs/architecture/graph-algorithm-backlog.md")

    assert "g_bipartite_endpoint_param_contract.py" in docs
    assert "G_bipartite_endpoint_param" in docs
    assert "G_http v1" in docs
    assert "raw parameter values" in " ".join(docs.lower().split())
    assert "snapshot_lineage_fields" in docs
    assert "edge_lineage_fields" in docs
    assert "not an IDOR finding" in docs
    assert "bipartite-endpoint-param-contract.md" in typed_doc
    assert "bipartite-endpoint-param-contract.md" in backlog
