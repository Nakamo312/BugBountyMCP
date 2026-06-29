from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path("services/graph-projector").resolve()))

from graph_projector.g_bipartite_endpoint_param_contract import ENDPOINT_PARAM_SIGNAL_SHAPES
from graph_projector.g_http_projection_contract import G_HTTP_PROJECTION_EVENT_SHAPE, G_HTTP_SIGNAL_SHAPES
from graph_projector.projection_contracts import AlgorithmFamily, get_projection_contract
from graph_projector.structural_signal_contract import (
    STRUCTURAL_SIGNAL_EVENT_SHAPE,
    STRUCTURAL_SIGNAL_EVENT_TYPE,
    STRUCTURAL_SIGNAL_FORBIDDEN_EVENT_FIELDS,
    STRUCTURAL_SIGNAL_FORBIDDEN_PAYLOAD_FIELDS,
    STRUCTURAL_SIGNAL_REQUIRED_EVENT_FIELDS,
    StructuralSignalEventShape,
    StructuralSignalTypeContract,
    structural_signal_contracts_by_type,
    structural_signal_type_names,
    validate_structural_signal_event_shape,
)


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_structural_signal_contract_validates_at_import_time() -> None:
    source = _read("services/graph-projector/graph_projector/structural_signal_contract.py")

    assert source.rstrip().endswith("validate_structural_signal_event_shape()")


def test_structural_signal_event_shape_is_contract_only_and_reference_based() -> None:
    shape = STRUCTURAL_SIGNAL_EVENT_SHAPE

    assert shape.event_type == STRUCTURAL_SIGNAL_EVENT_TYPE
    assert shape.contract_version == "v1"
    assert shape.status == "contract_only"
    assert set(STRUCTURAL_SIGNAL_REQUIRED_EVENT_FIELDS) <= set(shape.required_event_fields)
    assert set(shape.reference_fields) <= set(shape.required_event_fields)
    assert set(shape.score_fields) <= set(shape.required_event_fields)

    for forbidden in STRUCTURAL_SIGNAL_FORBIDDEN_EVENT_FIELDS:
        assert forbidden in shape.forbidden_event_fields
        assert forbidden not in shape.required_event_fields
    for raw_payload in (
        "raw_headers",
        "raw_request_body",
        "raw_response_body",
        "raw_url",
        "url_sample",
        "example_value",
        "raw_value",
        "secret_value",
        "authorization",
        "cookies",
    ):
        assert raw_payload in STRUCTURAL_SIGNAL_FORBIDDEN_PAYLOAD_FIELDS


def test_structural_signal_contracts_cover_g_http_and_endpoint_param_signal_shapes() -> None:
    signal_names = set(structural_signal_type_names())
    expected = {signal.signal_type for signal in G_HTTP_SIGNAL_SHAPES} | {
        signal.signal_type for signal in ENDPOINT_PARAM_SIGNAL_SHAPES
    }
    assert signal_names == expected

    contracts = structural_signal_contracts_by_type()
    assert contracts["HttpCoverageGapSignal"].projection_name == "G_http"
    assert contracts["MissingEndpointParamCandidateSignal"].projection_name == "G_bipartite_endpoint_param"
    assert contracts["HttpCoverageGapSignal"].source_event_type == "G_http_projection_snapshot_ready"
    assert contracts["MissingEndpointParamCandidateSignal"].source_event_type == (
        "G_bipartite_endpoint_param_projection_snapshot_ready"
    )


def test_structural_signal_contracts_match_projection_contract_algorithm_mappings() -> None:
    for signal in STRUCTURAL_SIGNAL_EVENT_SHAPE.signal_type_contracts:
        projection_contract = get_projection_contract(signal.projection_name)
        expected_algorithms = {
            item.signal_type: set(item.algorithm_families)
            for item in projection_contract.output_signal_families
        }
        assert signal.projection_contract_version == projection_contract.contract_version
        assert signal.signal_type in expected_algorithms
        assert set(signal.algorithm_families) == expected_algorithms[signal.signal_type]
        assert {"program_id", "projection_name", "projection_contract_version", "projection_snapshot_id"} <= set(
            signal.required_lineage_fields
        )
        assert signal.evidence_ref_fields
        assert set(signal.evidence_ref_fields).isdisjoint(set(signal.forbidden_payload_fields))


def test_structural_signal_event_shape_validation_rejects_findings_actions_and_raw_payloads() -> None:
    valid = STRUCTURAL_SIGNAL_EVENT_SHAPE
    with_finding_field = StructuralSignalEventShape(
        event_type=valid.event_type,
        contract_version=valid.contract_version,
        required_event_fields=valid.required_event_fields + ("finding_id",),
        reference_fields=valid.reference_fields,
        score_fields=valid.score_fields,
        signal_type_contracts=valid.signal_type_contracts,
        forbidden_event_fields=valid.forbidden_event_fields,
        forbidden_payload_fields=valid.forbidden_payload_fields,
    )
    try:
        validate_structural_signal_event_shape(with_finding_field)
    except ValueError as exc:
        assert "finding/action/command" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("structural signal event shape accepted finding/action fields")

    raw_evidence_signal = StructuralSignalTypeContract(
        signal_type="HttpCoverageGapSignal",
        projection_name="G_http",
        projection_contract_version="v1",
        source_event_type="G_http_projection_snapshot_ready",
        algorithm_families=(AlgorithmFamily.COVERAGE_SUMMARY,),
        required_lineage_fields=(
            "program_id",
            "projection_name",
            "projection_contract_version",
            "projection_snapshot_id",
        ),
        evidence_ref_fields=("raw_url",),
        forbidden_payload_fields=("raw_url",),
    )
    with_raw_evidence = StructuralSignalEventShape(
        event_type=valid.event_type,
        contract_version=valid.contract_version,
        required_event_fields=valid.required_event_fields,
        reference_fields=valid.reference_fields,
        score_fields=valid.score_fields,
        signal_type_contracts=(raw_evidence_signal,),
        forbidden_event_fields=valid.forbidden_event_fields,
        forbidden_payload_fields=valid.forbidden_payload_fields,
    )
    try:
        validate_structural_signal_event_shape(with_raw_evidence)
    except ValueError as exc:
        assert "forbidden payload" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("structural signal event shape accepted raw payload evidence refs")


def test_structural_signal_event_shape_validation_rejects_signal_mapping_drift() -> None:
    valid = STRUCTURAL_SIGNAL_EVENT_SHAPE
    wrong_projection_signal = StructuralSignalTypeContract(
        signal_type="HttpCoverageGapSignal",
        projection_name="G_bipartite_endpoint_param",
        projection_contract_version="v1",
        source_event_type="G_bipartite_endpoint_param_projection_snapshot_ready",
        algorithm_families=(AlgorithmFamily.COVERAGE_SUMMARY,),
        required_lineage_fields=(
            "program_id",
            "projection_name",
            "projection_contract_version",
            "projection_snapshot_id",
        ),
        evidence_ref_fields=("endpoint_ids",),
        forbidden_payload_fields=("raw_url",),
    )
    bad_shape = StructuralSignalEventShape(
        event_type=valid.event_type,
        contract_version=valid.contract_version,
        required_event_fields=valid.required_event_fields,
        reference_fields=valid.reference_fields,
        score_fields=valid.score_fields,
        signal_type_contracts=(wrong_projection_signal,),
        forbidden_event_fields=valid.forbidden_event_fields,
        forbidden_payload_fields=valid.forbidden_payload_fields,
    )
    try:
        validate_structural_signal_event_shape(bad_shape)
    except ValueError as exc:
        assert "is not declared" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("structural signal event shape accepted signal/projection drift")

    wrong_source_event_signal = StructuralSignalTypeContract(
        signal_type="HttpCoverageGapSignal",
        projection_name="G_http",
        projection_contract_version="v1",
        source_event_type="G_bipartite_endpoint_param_projection_snapshot_ready",
        algorithm_families=(AlgorithmFamily.COVERAGE_SUMMARY,),
        required_lineage_fields=(
            "program_id",
            "projection_name",
            "projection_contract_version",
            "projection_snapshot_id",
        ),
        evidence_ref_fields=("endpoint_ids",),
        forbidden_payload_fields=("raw_url",),
    )
    bad_source_event = StructuralSignalEventShape(
        event_type=valid.event_type,
        contract_version=valid.contract_version,
        required_event_fields=valid.required_event_fields,
        reference_fields=valid.reference_fields,
        score_fields=valid.score_fields,
        signal_type_contracts=(wrong_source_event_signal,),
        forbidden_event_fields=valid.forbidden_event_fields,
        forbidden_payload_fields=valid.forbidden_payload_fields,
    )
    try:
        validate_structural_signal_event_shape(bad_source_event)
    except ValueError as exc:
        assert "source_event_type does not match" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("structural signal event shape accepted projection/source event drift")

    wrong_algorithm_signal = StructuralSignalTypeContract(
        signal_type="HttpCoverageGapSignal",
        projection_name="G_http",
        projection_contract_version="v1",
        source_event_type="G_http_projection_snapshot_ready",
        algorithm_families=(AlgorithmFamily.DEGREE,),
        required_lineage_fields=(
            "program_id",
            "projection_name",
            "projection_contract_version",
            "projection_snapshot_id",
        ),
        evidence_ref_fields=("endpoint_ids",),
        forbidden_payload_fields=("raw_url",),
    )
    bad_algorithm = StructuralSignalEventShape(
        event_type=valid.event_type,
        contract_version=valid.contract_version,
        required_event_fields=valid.required_event_fields,
        reference_fields=valid.reference_fields,
        score_fields=valid.score_fields,
        signal_type_contracts=(wrong_algorithm_signal,),
        forbidden_event_fields=valid.forbidden_event_fields,
        forbidden_payload_fields=valid.forbidden_payload_fields,
    )
    try:
        validate_structural_signal_event_shape(bad_algorithm)
    except ValueError as exc:
        assert "algorithm families drifted" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("structural signal event shape accepted algorithm family drift")


def test_g_http_projection_event_type_is_ready_output_before_structural_signals() -> None:
    assert G_HTTP_PROJECTION_EVENT_SHAPE.event_type == "G_http_projection_snapshot_ready"


def test_structural_signal_event_model_is_documented_and_shape_only() -> None:
    docs = _read("docs/architecture/structural-signal-event-model.md")
    backlog = _read("docs/architecture/graph-algorithm-backlog.md")
    typed = _read("docs/architecture/typed-graph-projections.md")
    source = _read("services/graph-projector/graph_projector/structural_signal_contract.py")

    assert "structural_signal_contract.py" in docs
    assert "signal != finding" in docs
    assert "signal != action" in docs
    assert "node_refs" in docs
    assert "edge_refs" in docs
    assert "evidence_refs" in docs
    assert "structural-signal-event-model.md" in backlog
    assert "structural-signal-event-model.md" in typed
    for forbidden_runtime_marker in ("GraphDatabase", "gds.", "session.run", "CREATE", "MERGE", "ActionService"):
        assert forbidden_runtime_marker not in source
