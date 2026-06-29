from __future__ import annotations

from dataclasses import dataclass

from .g_bipartite_endpoint_param_contract import ENDPOINT_PARAM_PROJECTION_EVENT_SHAPE
from .g_http_projection_contract import G_HTTP_PROJECTION_EVENT_SHAPE
from .projection_contracts import AlgorithmFamily, get_projection_contract


@dataclass(frozen=True, slots=True)
class StructuralSignalTypeContract:
    """Contract metadata for one structural signal type.

    This is not a runtime signal class. It describes the durable event/read-model
    shape needed to carry a graph-derived structural signal without promoting it
    to a finding, action proposal, or tool execution request.
    """

    signal_type: str
    projection_name: str
    projection_contract_version: str
    source_event_type: str
    algorithm_families: tuple[AlgorithmFamily, ...]
    required_lineage_fields: tuple[str, ...]
    evidence_ref_fields: tuple[str, ...]
    forbidden_payload_fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StructuralSignalEventShape:
    """Shape inventory for durable structural signal events.

    The event shape is contract-only. It specifies references, lineage, scores,
    and generation metadata. It deliberately excludes finding/action fields and
    raw payloads.
    """

    event_type: str
    contract_version: str
    required_event_fields: tuple[str, ...]
    reference_fields: tuple[str, ...]
    score_fields: tuple[str, ...]
    signal_type_contracts: tuple[StructuralSignalTypeContract, ...]
    forbidden_event_fields: tuple[str, ...]
    forbidden_payload_fields: tuple[str, ...]
    status: str = "contract_only"


STRUCTURAL_SIGNAL_EVENT_TYPE = "structural_signal_generated"
STRUCTURAL_SIGNAL_CONTRACT_VERSION = "v1"

STRUCTURAL_SIGNAL_REQUIRED_EVENT_FIELDS: tuple[str, ...] = (
    "signal_id",
    "signal_type",
    "program_id",
    "projection_name",
    "projection_contract_version",
    "projection_snapshot_id",
    "algorithm_families",
    "score",
    "confidence",
    "node_refs",
    "edge_refs",
    "evidence_refs",
    "source_event_id",
    "generated_by",
    "generated_at",
)

STRUCTURAL_SIGNAL_REFERENCE_FIELDS: tuple[str, ...] = (
    "node_refs",
    "edge_refs",
    "evidence_refs",
    "source_event_id",
    "projection_snapshot_id",
)

STRUCTURAL_SIGNAL_SCORE_FIELDS: tuple[str, ...] = (
    "score",
    "confidence",
)

STRUCTURAL_SIGNAL_FORBIDDEN_EVENT_FIELDS: tuple[str, ...] = (
    "finding_id",
    "finding_status",
    "action_id",
    "action_proposal_id",
    "approval_request_id",
    "command_invocation_id",
    "command_argv",
    "credential_secret_version_id",
    "credential_lease_id",
)

STRUCTURAL_SIGNAL_FORBIDDEN_PAYLOAD_FIELDS: tuple[str, ...] = (
    "raw_headers",
    "raw_request_body",
    "raw_response_body",
    "raw_body",
    "body_preview",
    "raw_url",
    "full_url",
    "url_sample",
    "query",
    "fragment",
    "example_value",
    "raw_value",
    "secret_value",
    "query_value",
    "authorization",
    "cookies",
    "token",
    "secret",
    "password",
    "api_key",
    "session_cookie",
)


def _signal_contracts_from_projection_shape(
    *,
    projection_name: str,
    projection_contract_version: str,
    source_event_type: str,
    structural_signals: tuple[object, ...],
) -> tuple[StructuralSignalTypeContract, ...]:
    return tuple(
        StructuralSignalTypeContract(
            signal_type=signal.signal_type,
            projection_name=projection_name,
            projection_contract_version=projection_contract_version,
            source_event_type=source_event_type,
            algorithm_families=tuple(signal.algorithm_families),
            required_lineage_fields=tuple(signal.required_lineage_fields),
            evidence_ref_fields=tuple(signal.evidence_ref_fields),
            forbidden_payload_fields=tuple(signal.forbidden_payload_fields),
        )
        for signal in structural_signals
    )


STRUCTURAL_SIGNAL_TYPE_CONTRACTS: tuple[StructuralSignalTypeContract, ...] = (
    *_signal_contracts_from_projection_shape(
        projection_name=G_HTTP_PROJECTION_EVENT_SHAPE.projection_name,
        projection_contract_version=G_HTTP_PROJECTION_EVENT_SHAPE.contract_version,
        source_event_type=G_HTTP_PROJECTION_EVENT_SHAPE.event_type,
        structural_signals=G_HTTP_PROJECTION_EVENT_SHAPE.structural_signals,
    ),
    *_signal_contracts_from_projection_shape(
        projection_name=ENDPOINT_PARAM_PROJECTION_EVENT_SHAPE.projection_name,
        projection_contract_version=ENDPOINT_PARAM_PROJECTION_EVENT_SHAPE.contract_version,
        source_event_type=ENDPOINT_PARAM_PROJECTION_EVENT_SHAPE.event_type,
        structural_signals=ENDPOINT_PARAM_PROJECTION_EVENT_SHAPE.structural_signals,
    ),
)

STRUCTURAL_SIGNAL_EVENT_SHAPE = StructuralSignalEventShape(
    event_type=STRUCTURAL_SIGNAL_EVENT_TYPE,
    contract_version=STRUCTURAL_SIGNAL_CONTRACT_VERSION,
    required_event_fields=STRUCTURAL_SIGNAL_REQUIRED_EVENT_FIELDS,
    reference_fields=STRUCTURAL_SIGNAL_REFERENCE_FIELDS,
    score_fields=STRUCTURAL_SIGNAL_SCORE_FIELDS,
    signal_type_contracts=STRUCTURAL_SIGNAL_TYPE_CONTRACTS,
    forbidden_event_fields=STRUCTURAL_SIGNAL_FORBIDDEN_EVENT_FIELDS,
    forbidden_payload_fields=STRUCTURAL_SIGNAL_FORBIDDEN_PAYLOAD_FIELDS,
)

_EXPECTED_SOURCE_EVENT_BY_PROJECTION: dict[str, str] = {
    G_HTTP_PROJECTION_EVENT_SHAPE.projection_name: G_HTTP_PROJECTION_EVENT_SHAPE.event_type,
    ENDPOINT_PARAM_PROJECTION_EVENT_SHAPE.projection_name: ENDPOINT_PARAM_PROJECTION_EVENT_SHAPE.event_type,
}


def structural_signal_type_names(
    event_shape: StructuralSignalEventShape = STRUCTURAL_SIGNAL_EVENT_SHAPE,
) -> tuple[str, ...]:
    return tuple(signal.signal_type for signal in event_shape.signal_type_contracts)


def structural_signal_contracts_by_type(
    event_shape: StructuralSignalEventShape = STRUCTURAL_SIGNAL_EVENT_SHAPE,
) -> dict[str, StructuralSignalTypeContract]:
    return {signal.signal_type: signal for signal in event_shape.signal_type_contracts}


def validate_structural_signal_event_shape(
    event_shape: StructuralSignalEventShape = STRUCTURAL_SIGNAL_EVENT_SHAPE,
) -> None:
    if event_shape.event_type != STRUCTURAL_SIGNAL_EVENT_TYPE:
        raise ValueError("structural signal event shape must use structural_signal_generated")
    if event_shape.contract_version != STRUCTURAL_SIGNAL_CONTRACT_VERSION:
        raise ValueError("structural signal event shape contract_version must be v1")
    if event_shape.status != "contract_only":
        raise ValueError("structural signal event shape must remain contract_only until persistence exists")

    _require_non_empty_unique(event_shape.required_event_fields, "required_event_fields")
    _require_non_empty_unique(event_shape.reference_fields, "reference_fields")
    _require_non_empty_unique(event_shape.score_fields, "score_fields")
    _require_non_empty_unique(event_shape.forbidden_event_fields, "forbidden_event_fields")
    _require_non_empty_unique(event_shape.forbidden_payload_fields, "forbidden_payload_fields")

    required_fields = set(event_shape.required_event_fields)
    minimal_required = set(STRUCTURAL_SIGNAL_REQUIRED_EVENT_FIELDS)
    missing_required = minimal_required - required_fields
    if missing_required:
        raise ValueError(f"structural signal event shape missing required fields: {sorted(missing_required)}")

    forbidden_event_fields = set(event_shape.forbidden_event_fields)
    if required_fields & forbidden_event_fields:
        raise ValueError("structural signal event fields cannot include finding/action/command fields")

    if not set(event_shape.reference_fields) <= required_fields:
        raise ValueError("structural signal reference fields must be required event fields")
    if not set(event_shape.score_fields) <= required_fields:
        raise ValueError("structural signal score fields must be required event fields")

    signal_names = tuple(signal.signal_type for signal in event_shape.signal_type_contracts)
    if len(signal_names) != len(set(signal_names)):
        raise ValueError("structural signal type contracts must not contain duplicate signal types")

    forbidden_payloads = set(event_shape.forbidden_payload_fields)
    for signal in event_shape.signal_type_contracts:
        _validate_structural_signal_type_contract(signal, forbidden_payloads=forbidden_payloads)


def _validate_structural_signal_type_contract(
    signal: StructuralSignalTypeContract,
    *,
    forbidden_payloads: set[str],
) -> None:
    if not signal.signal_type.strip():
        raise ValueError("structural signal type must not be empty")
    if not signal.projection_name.startswith("G_"):
        raise ValueError("structural signal projection_name must reference a typed projection")
    if not signal.projection_contract_version.startswith("v"):
        raise ValueError("structural signal projection_contract_version must be versioned")
    if not signal.source_event_type.endswith("_projection_snapshot_ready"):
        raise ValueError("structural signals must be emitted from ready projection snapshot events")
    expected_source_event_type = _EXPECTED_SOURCE_EVENT_BY_PROJECTION.get(signal.projection_name)
    if expected_source_event_type is None:
        raise ValueError(f"{signal.signal_type} references unsupported projection {signal.projection_name}")
    if signal.source_event_type != expected_source_event_type:
        raise ValueError(
            f"{signal.signal_type} source_event_type does not match {signal.projection_name} snapshot event"
        )
    if not signal.required_lineage_fields:
        raise ValueError("structural signal required_lineage_fields must not be empty")
    if not signal.evidence_ref_fields:
        raise ValueError("structural signal evidence_ref_fields must not be empty")
    if not signal.algorithm_families:
        raise ValueError("structural signal algorithm_families must not be empty")

    projection_contract = get_projection_contract(signal.projection_name)
    if signal.projection_contract_version != projection_contract.contract_version:
        raise ValueError(
            f"{signal.signal_type} version drifted from {signal.projection_name} contract"
        )
    expected_signal_map = {
        output_signal.signal_type: set(output_signal.algorithm_families)
        for output_signal in projection_contract.output_signal_families
    }
    if signal.signal_type not in expected_signal_map:
        raise ValueError(
            f"{signal.signal_type} is not declared by {signal.projection_name} projection contract"
        )
    if set(signal.algorithm_families) != expected_signal_map[signal.signal_type]:
        raise ValueError(
            f"{signal.signal_type} algorithm families drifted from projection contract"
        )

    lineage_fields = set(signal.required_lineage_fields)
    if not {"program_id", "projection_name", "projection_contract_version", "projection_snapshot_id"} <= lineage_fields:
        raise ValueError(f"{signal.signal_type} missing minimal projection lineage fields")

    evidence_fields = set(signal.evidence_ref_fields)
    signal_forbidden = set(signal.forbidden_payload_fields)
    if evidence_fields & (forbidden_payloads | signal_forbidden):
        raise ValueError(f"{signal.signal_type} exposes forbidden payload fields as evidence refs")
    if lineage_fields & (forbidden_payloads | signal_forbidden):
        raise ValueError(f"{signal.signal_type} exposes forbidden payload fields as lineage")


def _require_non_empty_unique(values: tuple[str, ...], field_name: str) -> None:
    if not values:
        raise ValueError(f"{field_name} must not be empty")
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must not contain duplicates")


validate_structural_signal_event_shape()
