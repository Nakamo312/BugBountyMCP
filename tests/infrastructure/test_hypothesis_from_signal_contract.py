from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path("services/graph-projector").resolve()))

from graph_projector.hypothesis_from_signal_contract import (
    HYPOTHESIS_FROM_SIGNAL_ALLOWED_STATUSES,
    HYPOTHESIS_FROM_SIGNAL_EVENT_SHAPE,
    HYPOTHESIS_FROM_SIGNAL_EVENT_TYPE,
    HYPOTHESIS_FROM_SIGNAL_FORBIDDEN_EVENT_FIELDS,
    HYPOTHESIS_FROM_SIGNAL_FORBIDDEN_PAYLOAD_FIELDS,
    HYPOTHESIS_FROM_SIGNAL_REQUIRED_EVENT_FIELDS,
    HypothesisFromSignalEventShape,
    HypothesisProposalTypeContract,
    NumericFieldContract,
    hypothesis_proposal_contracts_by_type,
    hypothesis_proposal_types,
    validate_hypothesis_from_signal_event_shape,
)
from graph_projector.structural_signal_contract import (
    STRUCTURAL_SIGNAL_EVENT_TYPE,
    structural_signal_contracts_by_type,
    structural_signal_type_names,
)


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _shape_with(*, proposal_contracts: tuple[HypothesisProposalTypeContract, ...]) -> HypothesisFromSignalEventShape:
    valid = HYPOTHESIS_FROM_SIGNAL_EVENT_SHAPE
    return HypothesisFromSignalEventShape(
        event_type=valid.event_type,
        contract_version=valid.contract_version,
        source_event_type=valid.source_event_type,
        required_event_fields=valid.required_event_fields,
        reference_fields=valid.reference_fields,
        numeric_fields=valid.numeric_fields,
        proposal_type_contracts=proposal_contracts,
        allowed_statuses=valid.allowed_statuses,
        forbidden_event_fields=valid.forbidden_event_fields,
        forbidden_payload_fields=valid.forbidden_payload_fields,
    )


def test_hypothesis_from_signal_contract_validates_at_import_time() -> None:
    source = _read("services/graph-projector/graph_projector/hypothesis_from_signal_contract.py")

    assert source.rstrip().endswith("validate_hypothesis_from_signal_event_shape()")


def test_hypothesis_from_signal_event_shape_is_contract_only_and_review_based() -> None:
    shape = HYPOTHESIS_FROM_SIGNAL_EVENT_SHAPE

    assert shape.event_type == HYPOTHESIS_FROM_SIGNAL_EVENT_TYPE
    assert shape.contract_version == "v1"
    assert shape.source_event_type == STRUCTURAL_SIGNAL_EVENT_TYPE
    assert shape.status == "contract_only"
    assert set(HYPOTHESIS_FROM_SIGNAL_REQUIRED_EVENT_FIELDS) <= set(shape.required_event_fields)
    assert set(shape.reference_fields) <= set(shape.required_event_fields)
    assert "needs_review" in HYPOTHESIS_FROM_SIGNAL_ALLOWED_STATUSES

    for numeric in shape.numeric_fields:
        assert numeric.field_name in shape.required_event_fields
        assert numeric.minimum < numeric.maximum
    assert hypothesis_proposal_contracts_by_type()["http_coverage_gap_review"].hypothesis_type == (
        "graph_http_coverage_gap_followup"
    )


def test_hypothesis_proposal_contracts_cover_structural_signal_types_exactly_once() -> None:
    covered: list[str] = []
    known_signals = structural_signal_contracts_by_type()

    for contract in HYPOTHESIS_FROM_SIGNAL_EVENT_SHAPE.proposal_type_contracts:
        assert contract.proposal_type in hypothesis_proposal_types()
        assert contract.source_signal_types
        for signal_type in contract.source_signal_types:
            assert signal_type in known_signals
            covered.append(signal_type)
            signal_contract = known_signals[signal_type]
            assert set(contract.required_evidence_ref_fields) & set(signal_contract.evidence_ref_fields)
        assert "human_review" in contract.allowed_next_steps
        assert "evidence_critic_task" in contract.allowed_next_steps
        assert "tool_run" not in contract.allowed_next_steps
        assert "command_invocation" not in contract.allowed_next_steps

    assert set(covered) == set(structural_signal_type_names())
    assert len(covered) == len(set(covered))


def test_hypothesis_from_signal_event_shape_rejects_action_finding_and_raw_payload_fields() -> None:
    valid = HYPOTHESIS_FROM_SIGNAL_EVENT_SHAPE
    with_action_field = HypothesisFromSignalEventShape(
        event_type=valid.event_type,
        contract_version=valid.contract_version,
        source_event_type=valid.source_event_type,
        required_event_fields=valid.required_event_fields + ("action_proposal_id",),
        reference_fields=valid.reference_fields,
        numeric_fields=valid.numeric_fields,
        proposal_type_contracts=valid.proposal_type_contracts,
        allowed_statuses=valid.allowed_statuses,
        forbidden_event_fields=valid.forbidden_event_fields,
        forbidden_payload_fields=valid.forbidden_payload_fields,
    )
    try:
        validate_hypothesis_from_signal_event_shape(with_action_field)
    except ValueError as exc:
        assert "finding/action/command" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("hypothesis proposal event shape accepted action/finding fields")

    bad_contract = HypothesisProposalTypeContract(
        proposal_type="bad_raw_payload_review",
        source_signal_types=("HttpCoverageGapSignal",),
        hypothesis_type="bad_raw_payload_followup",
        required_evidence_ref_fields=("source_signal_ids", "endpoint_ids", "raw_url"),
        required_missing_observation_fields=("coverage_notes",),
        allowed_next_steps=("human_review", "evidence_critic_task"),
        forbidden_interpretations=("raw payload is not a finding",),
    )
    try:
        validate_hypothesis_from_signal_event_shape(_shape_with(proposal_contracts=(bad_contract,)))
    except ValueError as exc:
        assert "forbidden payload" in str(exc) or "drifted" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("hypothesis proposal accepted raw payload evidence")


def test_hypothesis_from_signal_event_shape_rejects_mapping_drift_and_execution_steps() -> None:
    unknown_signal = HypothesisProposalTypeContract(
        proposal_type="unknown_signal_review",
        source_signal_types=("UnknownSignal",),
        hypothesis_type="unknown_signal_followup",
        required_evidence_ref_fields=("source_signal_ids", "evidence_refs"),
        required_missing_observation_fields=("coverage_notes",),
        allowed_next_steps=("human_review", "evidence_critic_task"),
        forbidden_interpretations=("unknown signal is not a finding",),
    )
    try:
        validate_hypothesis_from_signal_event_shape(_shape_with(proposal_contracts=(unknown_signal,)))
    except ValueError as exc:
        assert "unknown structural signal" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("hypothesis proposal accepted unknown signal type")

    executable_step = HypothesisProposalTypeContract(
        proposal_type="bad_execution_review",
        source_signal_types=("HttpCoverageGapSignal",),
        hypothesis_type="bad_execution_followup",
        required_evidence_ref_fields=("source_signal_ids", "endpoint_ids"),
        required_missing_observation_fields=("coverage_notes",),
        allowed_next_steps=("human_review", "evidence_critic_task", "tool_run"),
        forbidden_interpretations=("execution candidate is not a finding",),
    )
    try:
        validate_hypothesis_from_signal_event_shape(_shape_with(proposal_contracts=(executable_step,)))
    except ValueError as exc:
        assert "cannot authorize execution" in str(exc) or "drifted" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("hypothesis proposal accepted direct execution step")


def test_hypothesis_from_signal_event_shape_rejects_bad_source_and_numeric_contracts() -> None:
    valid = HYPOTHESIS_FROM_SIGNAL_EVENT_SHAPE
    bad_source = HypothesisFromSignalEventShape(
        event_type=valid.event_type,
        contract_version=valid.contract_version,
        source_event_type="G_http_projection_snapshot_ready",
        required_event_fields=valid.required_event_fields,
        reference_fields=valid.reference_fields,
        numeric_fields=valid.numeric_fields,
        proposal_type_contracts=valid.proposal_type_contracts,
        allowed_statuses=valid.allowed_statuses,
        forbidden_event_fields=valid.forbidden_event_fields,
        forbidden_payload_fields=valid.forbidden_payload_fields,
    )
    try:
        validate_hypothesis_from_signal_event_shape(bad_source)
    except ValueError as exc:
        assert "structural_signal_generated" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("hypothesis proposal accepted non-structural-signal source event")

    bad_numeric = HypothesisFromSignalEventShape(
        event_type=valid.event_type,
        contract_version=valid.contract_version,
        source_event_type=valid.source_event_type,
        required_event_fields=valid.required_event_fields,
        reference_fields=valid.reference_fields,
        numeric_fields=(NumericFieldContract("confidence", 1.0, 0.0, "bad range"),),
        proposal_type_contracts=valid.proposal_type_contracts,
        allowed_statuses=valid.allowed_statuses,
        forbidden_event_fields=valid.forbidden_event_fields,
        forbidden_payload_fields=valid.forbidden_payload_fields,
    )
    try:
        validate_hypothesis_from_signal_event_shape(bad_numeric)
    except ValueError as exc:
        assert "invalid range" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("hypothesis proposal accepted invalid numeric range")


def test_hypothesis_from_signal_contract_is_documented_and_shape_only() -> None:
    docs = _read("docs/architecture/hypothesis-from-structural-signal-contract.md")
    signal_docs = _read("docs/architecture/structural-signal-event-model.md")
    backlog = _read("docs/architecture/graph-algorithm-backlog.md")
    source = _read("services/graph-projector/graph_projector/hypothesis_from_signal_contract.py")

    assert "hypothesis_from_signal_contract.py" in docs
    assert "StructuralSignal -> HypothesisProposal" in docs
    assert "hypothesis proposal != finding" in docs
    assert "hypothesis proposal != action proposal" in docs
    assert "hypothesis-from-structural-signal-contract.md" in signal_docs
    assert "hypothesis-from-structural-signal-contract.md" in backlog
    for forbidden_runtime_marker in (
        "GraphDatabase",
        "gds.",
        "session.run",
        "CREATE",
        "MERGE",
        "ActionService",
        "CommandInvocation",
    ):
        assert forbidden_runtime_marker not in source
    for forbidden_field in HYPOTHESIS_FROM_SIGNAL_FORBIDDEN_EVENT_FIELDS:
        assert forbidden_field not in HYPOTHESIS_FROM_SIGNAL_REQUIRED_EVENT_FIELDS
    for raw_payload in ("raw_url", "raw_payload", "exploit_steps", "curl_command"):
        assert raw_payload in HYPOTHESIS_FROM_SIGNAL_FORBIDDEN_PAYLOAD_FIELDS
