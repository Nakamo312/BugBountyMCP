from __future__ import annotations

from dataclasses import dataclass

from .structural_signal_contract import (
    STRUCTURAL_SIGNAL_EVENT_SHAPE,
    STRUCTURAL_SIGNAL_EVENT_TYPE,
    STRUCTURAL_SIGNAL_FORBIDDEN_EVENT_FIELDS,
    STRUCTURAL_SIGNAL_FORBIDDEN_PAYLOAD_FIELDS,
    structural_signal_contracts_by_type,
    structural_signal_type_names,
)


@dataclass(frozen=True, slots=True)
class NumericFieldContract:
    """Numeric bound for a proposal event field.

    This is shape-level validation. Runtime payload validation must still enforce
    these ranges when proposal persistence exists.
    """

    field_name: str
    minimum: float
    maximum: float
    semantics: str


@dataclass(frozen=True, slots=True)
class HypothesisProposalTypeContract:
    """Mapping from structural signal types to hypothesis proposal types.

    A proposal type names a review target produced from one or more structural
    signals. It is not a finding, action proposal, or tool execution request.
    """

    proposal_type: str
    source_signal_types: tuple[str, ...]
    hypothesis_type: str
    required_evidence_ref_fields: tuple[str, ...]
    required_missing_observation_fields: tuple[str, ...]
    allowed_next_steps: tuple[str, ...]
    forbidden_interpretations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HypothesisFromSignalEventShape:
    """Contract-only shape for structural-signal-derived hypothesis proposals."""

    event_type: str
    contract_version: str
    source_event_type: str
    required_event_fields: tuple[str, ...]
    reference_fields: tuple[str, ...]
    numeric_fields: tuple[NumericFieldContract, ...]
    proposal_type_contracts: tuple[HypothesisProposalTypeContract, ...]
    allowed_statuses: tuple[str, ...]
    forbidden_event_fields: tuple[str, ...]
    forbidden_payload_fields: tuple[str, ...]
    status: str = "contract_only"


HYPOTHESIS_FROM_SIGNAL_EVENT_TYPE = "hypothesis_proposal_created"
HYPOTHESIS_FROM_SIGNAL_CONTRACT_VERSION = "v1"
HYPOTHESIS_FROM_SIGNAL_SOURCE_EVENT_TYPE = STRUCTURAL_SIGNAL_EVENT_TYPE

HYPOTHESIS_FROM_SIGNAL_REQUIRED_EVENT_FIELDS: tuple[str, ...] = (
    "proposal_id",
    "proposal_type",
    "hypothesis_type",
    "program_id",
    "status",
    "source_signal_ids",
    "source_signal_types",
    "projection_refs",
    "evidence_refs",
    "missing_observations",
    "confidence",
    "priority_score",
    "safety_level",
    "score_version",
    "source_event_ids",
    "generated_by",
    "generated_at",
)

HYPOTHESIS_FROM_SIGNAL_REFERENCE_FIELDS: tuple[str, ...] = (
    "source_signal_ids",
    "projection_refs",
    "evidence_refs",
    "source_event_ids",
)

HYPOTHESIS_FROM_SIGNAL_NUMERIC_FIELDS: tuple[NumericFieldContract, ...] = (
    NumericFieldContract(
        field_name="confidence",
        minimum=0.0,
        maximum=1.0,
        semantics="confidence in the proposal framing, not proof of vulnerability",
    ),
    NumericFieldContract(
        field_name="priority_score",
        minimum=0.0,
        maximum=100.0,
        semantics="review prioritization score, not severity or exploitability",
    ),
)

HYPOTHESIS_FROM_SIGNAL_ALLOWED_STATUSES: tuple[str, ...] = (
    "proposed",
    "needs_review",
)

HYPOTHESIS_FROM_SIGNAL_FORBIDDEN_EVENT_FIELDS: tuple[str, ...] = tuple(
    dict.fromkeys(
        (
            *STRUCTURAL_SIGNAL_FORBIDDEN_EVENT_FIELDS,
            "finding_id",
            "finding_status",
            "action_id",
            "action_proposal_id",
            "approval_request_id",
            "command_invocation_id",
            "command_argv",
            "credential_secret_version_id",
            "credential_lease_id",
            "tool_name",
            "tool_args",
            "runner_id",
        )
    )
)

HYPOTHESIS_FROM_SIGNAL_FORBIDDEN_PAYLOAD_FIELDS: tuple[str, ...] = tuple(
    dict.fromkeys(
        (
            *STRUCTURAL_SIGNAL_FORBIDDEN_PAYLOAD_FIELDS,
            "raw_evidence",
            "raw_payload",
            "exploit_steps",
            "reproduction_steps",
            "command_template",
            "curl_command",
        )
    )
)

_ALLOWED_NEXT_STEPS: tuple[str, ...] = (
    "human_review",
    "rag_context_task",
    "rlm_deep_analysis_task",
    "evidence_critic_task",
    "action_proposal_draft",
)

_HYPOTHESIS_PROPOSAL_TYPE_CONTRACTS: tuple[HypothesisProposalTypeContract, ...] = (
    HypothesisProposalTypeContract(
        proposal_type="http_endpoint_neighborhood_review",
        source_signal_types=("HttpEndpointNeighborhoodSignal",),
        hypothesis_type="graph_http_endpoint_neighborhood_followup",
        required_evidence_ref_fields=("source_signal_ids", "endpoint_ids", "http_observation_ids"),
        required_missing_observation_fields=("coverage_notes", "sampled_endpoint_refs"),
        allowed_next_steps=_ALLOWED_NEXT_STEPS,
        forbidden_interpretations=(
            "endpoint neighborhood similarity is not a vulnerability finding",
            "similar routes do not authorize tool execution",
        ),
    ),
    HypothesisProposalTypeContract(
        proposal_type="http_coverage_gap_review",
        source_signal_types=("HttpCoverageGapSignal",),
        hypothesis_type="graph_http_coverage_gap_followup",
        required_evidence_ref_fields=("source_signal_ids", "endpoint_ids", "coverage_window_id"),
        required_missing_observation_fields=("missing_observation_refs", "coverage_scope_notes"),
        allowed_next_steps=_ALLOWED_NEXT_STEPS,
        forbidden_interpretations=(
            "coverage gap is not a finding",
            "coverage gap does not create an action approval",
        ),
    ),
    HypothesisProposalTypeContract(
        proposal_type="http_drift_review",
        source_signal_types=("HttpDriftSignal",),
        hypothesis_type="graph_http_drift_followup",
        required_evidence_ref_fields=("source_signal_ids", "previous_projection_snapshot_id", "current_projection_snapshot_id"),
        required_missing_observation_fields=("previous_snapshot_refs", "current_snapshot_refs"),
        allowed_next_steps=_ALLOWED_NEXT_STEPS,
        forbidden_interpretations=(
            "drift is not a finding",
            "drift does not imply vulnerability without evidence",
        ),
    ),
    HypothesisProposalTypeContract(
        proposal_type="http_missing_relation_review",
        source_signal_types=("HttpMissingRelationCandidateSignal",),
        hypothesis_type="graph_http_missing_relation_followup",
        required_evidence_ref_fields=("source_signal_ids", "endpoint_ids", "param_ids"),
        required_missing_observation_fields=("candidate_relation_refs", "neighbor_refs"),
        allowed_next_steps=_ALLOWED_NEXT_STEPS,
        forbidden_interpretations=(
            "missing relation candidate is advisory",
            "missing relation candidate is not a finding",
        ),
    ),
    HypothesisProposalTypeContract(
        proposal_type="endpoint_param_similarity_review",
        source_signal_types=("EndpointParamSimilaritySignal",),
        hypothesis_type="graph_endpoint_param_similarity_followup",
        required_evidence_ref_fields=("source_signal_ids", "endpoint_ids", "shared_param_ids"),
        required_missing_observation_fields=("comparison_endpoint_refs", "shared_param_refs"),
        allowed_next_steps=_ALLOWED_NEXT_STEPS,
        forbidden_interpretations=(
            "shared parameter neighborhood is not an IDOR finding",
            "similarity score is not authorization evidence",
        ),
    ),
    HypothesisProposalTypeContract(
        proposal_type="param_centrality_review",
        source_signal_types=("ParamCentralitySignal",),
        hypothesis_type="graph_param_centrality_followup",
        required_evidence_ref_fields=("source_signal_ids", "param_id", "endpoint_ids"),
        required_missing_observation_fields=("param_usage_refs", "coverage_notes"),
        allowed_next_steps=_ALLOWED_NEXT_STEPS,
        forbidden_interpretations=(
            "central parameter is not a finding",
            "centrality does not prove exploitability",
        ),
    ),
    HypothesisProposalTypeContract(
        proposal_type="missing_endpoint_param_candidate_review",
        source_signal_types=("MissingEndpointParamCandidateSignal",),
        hypothesis_type="graph_missing_endpoint_param_candidate_followup",
        required_evidence_ref_fields=(
            "source_signal_ids",
            "candidate_endpoint_id",
            "candidate_param_id",
            "neighbor_endpoint_ids",
        ),
        required_missing_observation_fields=("candidate_relation_refs", "neighbor_endpoint_refs"),
        allowed_next_steps=_ALLOWED_NEXT_STEPS,
        forbidden_interpretations=(
            "missing endpoint-param candidate is not an IDOR finding",
            "candidate edge does not authorize CLI execution",
        ),
    ),
)

HYPOTHESIS_FROM_SIGNAL_EVENT_SHAPE = HypothesisFromSignalEventShape(
    event_type=HYPOTHESIS_FROM_SIGNAL_EVENT_TYPE,
    contract_version=HYPOTHESIS_FROM_SIGNAL_CONTRACT_VERSION,
    source_event_type=HYPOTHESIS_FROM_SIGNAL_SOURCE_EVENT_TYPE,
    required_event_fields=HYPOTHESIS_FROM_SIGNAL_REQUIRED_EVENT_FIELDS,
    reference_fields=HYPOTHESIS_FROM_SIGNAL_REFERENCE_FIELDS,
    numeric_fields=HYPOTHESIS_FROM_SIGNAL_NUMERIC_FIELDS,
    proposal_type_contracts=_HYPOTHESIS_PROPOSAL_TYPE_CONTRACTS,
    allowed_statuses=HYPOTHESIS_FROM_SIGNAL_ALLOWED_STATUSES,
    forbidden_event_fields=HYPOTHESIS_FROM_SIGNAL_FORBIDDEN_EVENT_FIELDS,
    forbidden_payload_fields=HYPOTHESIS_FROM_SIGNAL_FORBIDDEN_PAYLOAD_FIELDS,
)


def hypothesis_proposal_types(
    event_shape: HypothesisFromSignalEventShape = HYPOTHESIS_FROM_SIGNAL_EVENT_SHAPE,
) -> tuple[str, ...]:
    return tuple(contract.proposal_type for contract in event_shape.proposal_type_contracts)


def hypothesis_proposal_contracts_by_type(
    event_shape: HypothesisFromSignalEventShape = HYPOTHESIS_FROM_SIGNAL_EVENT_SHAPE,
) -> dict[str, HypothesisProposalTypeContract]:
    return {contract.proposal_type: contract for contract in event_shape.proposal_type_contracts}


def validate_hypothesis_from_signal_event_shape(
    event_shape: HypothesisFromSignalEventShape = HYPOTHESIS_FROM_SIGNAL_EVENT_SHAPE,
) -> None:
    if event_shape.event_type != HYPOTHESIS_FROM_SIGNAL_EVENT_TYPE:
        raise ValueError("hypothesis-from-signal event shape must use hypothesis_proposal_created")
    if event_shape.contract_version != HYPOTHESIS_FROM_SIGNAL_CONTRACT_VERSION:
        raise ValueError("hypothesis-from-signal event shape contract_version must be v1")
    if event_shape.source_event_type != STRUCTURAL_SIGNAL_EVENT_TYPE:
        raise ValueError("hypothesis proposals must derive from structural_signal_generated")
    if event_shape.status != "contract_only":
        raise ValueError("hypothesis-from-signal shape must remain contract_only until persistence exists")

    _require_non_empty_unique(event_shape.required_event_fields, "required_event_fields")
    _require_non_empty_unique(event_shape.reference_fields, "reference_fields")
    _require_non_empty_unique(tuple(field.field_name for field in event_shape.numeric_fields), "numeric_fields")
    _require_non_empty_unique(event_shape.allowed_statuses, "allowed_statuses")
    _require_non_empty_unique(event_shape.forbidden_event_fields, "forbidden_event_fields")
    _require_non_empty_unique(event_shape.forbidden_payload_fields, "forbidden_payload_fields")

    required_fields = set(event_shape.required_event_fields)
    missing_required = set(HYPOTHESIS_FROM_SIGNAL_REQUIRED_EVENT_FIELDS) - required_fields
    if missing_required:
        raise ValueError(f"hypothesis proposal event shape missing required fields: {sorted(missing_required)}")

    forbidden_event_fields = set(event_shape.forbidden_event_fields)
    if required_fields & forbidden_event_fields:
        raise ValueError("hypothesis proposal event fields cannot include finding/action/command fields")
    if not set(event_shape.reference_fields) <= required_fields:
        raise ValueError("hypothesis proposal reference fields must be required event fields")

    for numeric in event_shape.numeric_fields:
        if numeric.field_name not in required_fields:
            raise ValueError(f"numeric field {numeric.field_name} must be required")
        if numeric.minimum >= numeric.maximum:
            raise ValueError(f"numeric field {numeric.field_name} has invalid range")

    if "needs_review" not in event_shape.allowed_statuses:
        raise ValueError("hypothesis proposals must support needs_review status")

    proposal_types = tuple(contract.proposal_type for contract in event_shape.proposal_type_contracts)
    if len(proposal_types) != len(set(proposal_types)):
        raise ValueError("hypothesis proposal type contracts must not contain duplicates")

    covered_signal_types: list[str] = []
    forbidden_payloads = set(event_shape.forbidden_payload_fields)
    for contract in event_shape.proposal_type_contracts:
        _validate_hypothesis_proposal_type_contract(contract, forbidden_payloads=forbidden_payloads)
        covered_signal_types.extend(contract.source_signal_types)

    expected_signal_types = set(structural_signal_type_names())
    covered = set(covered_signal_types)
    if covered != expected_signal_types:
        missing = sorted(expected_signal_types - covered)
        extra = sorted(covered - expected_signal_types)
        raise ValueError(f"hypothesis proposal contracts drifted from structural signals: missing={missing} extra={extra}")
    if len(covered_signal_types) != len(set(covered_signal_types)):
        raise ValueError("each structural signal type must map to exactly one hypothesis proposal type")


def _validate_hypothesis_proposal_type_contract(
    contract: HypothesisProposalTypeContract,
    *,
    forbidden_payloads: set[str],
) -> None:
    if not contract.proposal_type.strip():
        raise ValueError("proposal_type must not be empty")
    if not contract.hypothesis_type.strip():
        raise ValueError("hypothesis_type must not be empty")
    _require_non_empty_unique(contract.source_signal_types, "source_signal_types")
    _require_non_empty_unique(contract.required_evidence_ref_fields, "required_evidence_ref_fields")
    _require_non_empty_unique(contract.required_missing_observation_fields, "required_missing_observation_fields")
    _require_non_empty_unique(contract.allowed_next_steps, "allowed_next_steps")
    _require_non_empty_unique(contract.forbidden_interpretations, "forbidden_interpretations")

    known_signal_types = set(structural_signal_type_names())
    unknown_signal_types = set(contract.source_signal_types) - known_signal_types
    if unknown_signal_types:
        raise ValueError(f"{contract.proposal_type} references unknown structural signal types")

    by_signal_type = structural_signal_contracts_by_type()
    for signal_type in contract.source_signal_types:
        signal_contract = by_signal_type[signal_type]
        if not set(contract.required_evidence_ref_fields) & set(signal_contract.evidence_ref_fields):
            raise ValueError(f"{contract.proposal_type} does not preserve evidence refs from {signal_type}")

    if "source_signal_ids" not in contract.required_evidence_ref_fields:
        raise ValueError(f"{contract.proposal_type} must preserve source_signal_ids")
    if not {"human_review", "evidence_critic_task"} <= set(contract.allowed_next_steps):
        raise ValueError(f"{contract.proposal_type} must route through review/critic steps")
    if {"tool_run", "command_invocation", "action_execution", "auto_approve"} & set(contract.allowed_next_steps):
        raise ValueError(f"{contract.proposal_type} cannot authorize execution")

    evidence_fields = set(contract.required_evidence_ref_fields)
    missing_observation_fields = set(contract.required_missing_observation_fields)
    if evidence_fields & forbidden_payloads:
        raise ValueError(f"{contract.proposal_type} exposes forbidden payload fields as evidence refs")
    if missing_observation_fields & forbidden_payloads:
        raise ValueError(f"{contract.proposal_type} exposes forbidden payload fields as missing observations")

    forbidden_text = " ".join(contract.forbidden_interpretations).lower()
    for required_boundary_word in ("not", "finding"):
        if required_boundary_word not in forbidden_text:
            raise ValueError(f"{contract.proposal_type} must state that proposals are not findings/actions")


def _require_non_empty_unique(values: tuple[str, ...], field_name: str) -> None:
    if not values:
        raise ValueError(f"{field_name} must not be empty")
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must not contain duplicates")


validate_hypothesis_from_signal_event_shape()
