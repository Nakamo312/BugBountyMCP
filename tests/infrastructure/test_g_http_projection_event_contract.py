from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path("services/graph-projector").resolve()))

from graph_projector.g_http_projection_contract import (  # noqa: E402
    G_HTTP_EDGE_SHAPES,
    G_HTTP_LINEAGE_TABLES,
    G_HTTP_NODE_SHAPES,
    G_HTTP_PROJECTION_EVENT_SHAPE,
    G_HTTP_SIGNAL_SHAPES,
    G_HTTP_SOURCE_RECORD_TYPES,
    G_HTTP_SOURCE_TABLES,
    GHttpNodeShape,
    GHttpProjectionEventShape,
    validate_g_http_projection_event_shape,
    g_http_edge_types,
    g_http_node_types,
    g_http_signal_types,
)
from graph_projector.projection_contracts import AlgorithmFamily, get_projection_contract  # noqa: E402


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_g_http_projection_event_shape_references_versioned_projection_contract() -> None:
    contract = get_projection_contract("G_http")
    event_shape = G_HTTP_PROJECTION_EVENT_SHAPE

    assert event_shape.status == "contract_only"
    assert event_shape.projection_name == contract.name
    assert event_shape.contract_version == contract.contract_version
    assert event_shape.source_event_types == ("http_observations_ready",)
    assert set(g_http_node_types()).issubset(set(contract.node_types))
    assert set(g_http_edge_types()).issubset(set(contract.edge_types))
    assert set(g_http_signal_types()) == set(contract.output_signals)


def test_g_http_projection_event_shape_defines_minimal_http_surface_space() -> None:
    assert g_http_node_types() == (
        "endpoint",
        "route_template",
        "method",
        "param",
        "body_schema",
        "response_shape",
        "status_class",
        "content_type",
        "observed_action",
    )
    assert g_http_edge_types() == (
        "HAS_ROUTE_TEMPLATE",
        "USES_METHOD",
        "HAS_PARAM",
        "HAS_BODY_SCHEMA",
        "RETURNS_RESPONSE_SHAPE",
        "RETURNS_STATUS_CLASS",
        "RETURNS_CONTENT_TYPE",
        "OBSERVED_BY_ACTION",
    )
    assert {node.node_type for node in G_HTTP_NODE_SHAPES} == set(g_http_node_types())
    assert {edge.edge_type for edge in G_HTTP_EDGE_SHAPES} == set(g_http_edge_types())


def test_g_http_projection_event_shape_references_existing_canonical_record_types_and_tables() -> None:
    domain_models = _read("src/api/domain/models.py")
    table_sources = _read("src/api/infrastructure/adapters/orm_tables/search_projection.py") + _read(
        "src/api/infrastructure/adapters/orm_tables/inventory.py"
    ) + _read("src/api/infrastructure/adapters/orm_tables/action_execution.py")

    for record_type in G_HTTP_SOURCE_RECORD_TYPES:
        assert record_type in domain_models
    for table_name in G_HTTP_SOURCE_TABLES + G_HTTP_LINEAGE_TABLES:
        assert f"{table_name} = Table" in table_sources


def test_g_http_projection_event_shape_separates_source_records_from_lineage_tables() -> None:
    event_sources = set(G_HTTP_PROJECTION_EVENT_SHAPE.source_record_types)

    assert "RunModel" not in event_sources
    assert "RawArtifactModel" not in event_sources
    assert "ActionOutcomeModel" not in event_sources
    assert G_HTTP_PROJECTION_EVENT_SHAPE.lineage_tables == ("runs", "action_outcomes", "raw_artifacts")

    for node in G_HTTP_NODE_SHAPES:
        assert set(node.source_record_types) <= event_sources
    for edge in G_HTTP_EDGE_SHAPES:
        assert set(edge.source_record_types) <= event_sources


def test_g_http_projection_event_shape_requires_lineage_and_forbids_secret_payloads() -> None:
    required = set(G_HTTP_PROJECTION_EVENT_SHAPE.required_lineage_fields)
    for field in (
        "program_id",
        "projection_name",
        "projection_contract_version",
        "projection_snapshot_id",
        "http_observation_id",
        "endpoint_id",
        "service_id",
        "run_id",
        "raw_artifact_id",
        "normalization_version",
    ):
        assert field in required

    forbidden = "\n".join(G_HTTP_PROJECTION_EVENT_SHAPE.forbidden_payload_fields).lower()
    assert "authorization" in forbidden
    assert "cookies" in forbidden
    assert "raw_request_body" in forbidden
    assert "raw_response_body" in forbidden

    for node in G_HTTP_NODE_SHAPES:
        assert "authorization" not in node.required_properties
        assert "cookie" not in node.required_properties
        assert "url_sample" not in node.required_properties
        assert "url_sample" not in node.optional_properties
    assert any("raw_value" in node.forbidden_properties for node in G_HTTP_NODE_SHAPES)




def test_g_http_projection_event_shape_keeps_node_key_fields_available() -> None:
    lineage_fields = set(G_HTTP_PROJECTION_EVENT_SHAPE.required_lineage_fields)
    for node in G_HTTP_NODE_SHAPES:
        available_identity_fields = set(node.required_properties) | lineage_fields | set(node.identity_only_fields)
        assert set(node.key_fields) <= available_identity_fields


def test_g_http_projection_event_shape_validation_rejects_inconsistent_sources_and_keys() -> None:
    valid = G_HTTP_PROJECTION_EVENT_SHAPE

    node_with_unknown_source = GHttpNodeShape(
        node_type="bad_source",
        key_fields=("id",),
        required_properties=("id",),
        source_record_types=("RunModel",),
    )
    invalid_sources = GHttpProjectionEventShape(
        projection_name=valid.projection_name,
        contract_version=valid.contract_version,
        event_type=valid.event_type,
        source_event_types=valid.source_event_types,
        source_record_types=valid.source_record_types,
        source_tables=valid.source_tables,
        lineage_tables=valid.lineage_tables,
        required_lineage_fields=valid.required_lineage_fields,
        nodes=valid.nodes + (node_with_unknown_source,),
        edges=valid.edges,
        structural_signals=valid.structural_signals,
        forbidden_payload_fields=valid.forbidden_payload_fields,
    )
    try:
        validate_g_http_projection_event_shape(invalid_sources)
    except ValueError as exc:
        assert "non-source records" in str(exc)
    else:
        raise AssertionError("unknown source record should be rejected")

    node_with_missing_key = GHttpNodeShape(
        node_type="bad_key",
        key_fields=("missing_identity",),
        required_properties=("id",),
        source_record_types=("HTTPObservationModel",),
    )
    invalid_key = GHttpProjectionEventShape(
        projection_name=valid.projection_name,
        contract_version=valid.contract_version,
        event_type=valid.event_type,
        source_event_types=valid.source_event_types,
        source_record_types=valid.source_record_types,
        source_tables=valid.source_tables,
        lineage_tables=valid.lineage_tables,
        required_lineage_fields=valid.required_lineage_fields,
        nodes=valid.nodes + (node_with_missing_key,),
        edges=valid.edges,
        structural_signals=valid.structural_signals,
        forbidden_payload_fields=valid.forbidden_payload_fields,
    )
    try:
        validate_g_http_projection_event_shape(invalid_key)
    except ValueError as exc:
        assert "key fields" in str(exc)
    else:
        raise AssertionError("unavailable key field should be rejected")


def test_g_http_projection_event_shape_validation_rejects_raw_url_samples() -> None:
    valid = G_HTTP_PROJECTION_EVENT_SHAPE
    node_with_url_sample = GHttpNodeShape(
        node_type="bad_url_sample",
        key_fields=("id",),
        required_properties=("id",),
        optional_properties=("url_sample",),
        source_record_types=("HTTPObservationModel",),
    )
    invalid = GHttpProjectionEventShape(
        projection_name=valid.projection_name,
        contract_version=valid.contract_version,
        event_type=valid.event_type,
        source_event_types=valid.source_event_types,
        source_record_types=valid.source_record_types,
        source_tables=valid.source_tables,
        lineage_tables=valid.lineage_tables,
        required_lineage_fields=valid.required_lineage_fields,
        nodes=valid.nodes + (node_with_url_sample,),
        edges=valid.edges,
        structural_signals=valid.structural_signals,
        forbidden_payload_fields=valid.forbidden_payload_fields,
    )
    try:
        validate_g_http_projection_event_shape(invalid)
    except ValueError as exc:
        assert "raw URL/sample" in str(exc)
    else:
        raise AssertionError("raw URL sample property should be rejected")


def test_g_http_signal_shapes_map_to_allowed_algorithm_families() -> None:
    contract = get_projection_contract("G_http")
    contract_signal_map = {
        signal.signal_type: set(signal.algorithm_families)
        for signal in contract.output_signal_families
    }

    for signal in G_HTTP_SIGNAL_SHAPES:
        assert set(signal.algorithm_families) == contract_signal_map[signal.signal_type]
        assert set(signal.algorithm_families).issubset(set(contract.algorithm_families))
        assert "projection_snapshot_id" in signal.required_lineage_fields
        assert signal.evidence_ref_fields
        assert signal.forbidden_payload_fields

    assert contract_signal_map["HttpCoverageGapSignal"] == {AlgorithmFamily.COVERAGE_SUMMARY}
    assert contract_signal_map["HttpDriftSignal"] == {AlgorithmFamily.DRIFT_SUMMARY}


def test_g_http_projection_contract_is_shape_only_not_runtime_gds() -> None:
    source = _read("services/graph-projector/graph_projector/g_http_projection_contract.py")

    assert "GraphDatabase" not in source
    assert "gds." not in source
    assert "session.run" not in source
    assert "CREATE" not in source
    assert "MERGE" not in source
    assert "ActionService" not in source
