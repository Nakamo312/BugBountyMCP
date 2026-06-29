from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


_REQUIRED_TEXT_SEQUENCE_FIELDS = (
    "input_facts",
    "node_types",
    "edge_types",
    "allowed_algorithms",
    "output_signals",
    "lineage_requirements",
    "sensitivity_rules",
    "forbidden_interpretations",
    "failure_modes",
)


class AlgorithmFamily(str, Enum):
    WCC = "weakly_connected_components"
    DEGREE = "degree"
    CENTRALITY = "centrality"
    JACCARD_SIMILARITY = "jaccard_similarity"
    BIPARTITE_LINK_PREDICTION_BASELINE = "bipartite_link_prediction_baseline"
    COVERAGE_SUMMARY = "coverage_summary"
    DRIFT_SUMMARY = "drift_summary"
    TEMPORAL_CO_CHANGE = "temporal_co_change"
    NOVELTY_DECAY = "novelty_decay"
    EVIDENCE_SIMILARITY = "evidence_similarity"
    DUPLICATE_GROUPING = "duplicate_grouping"
    REACHABILITY_SUMMARY = "reachability_summary"


@dataclass(frozen=True, slots=True)
class SignalAlgorithmContract:
    """Allowed algorithm-family mapping for one structural signal type.

    This is still contract metadata, not a signal implementation class. It only
    prevents a projection contract from claiming one set of algorithm families
    while advertising unrelated signal types.
    """

    signal_type: str
    algorithm_families: tuple[AlgorithmFamily, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "signal_type", _clean_text(self.signal_type, "signal_type"))
        object.__setattr__(
            self,
            "algorithm_families",
            _clean_algorithm_families(self.algorithm_families),
        )


@dataclass(frozen=True, slots=True)
class ProjectionContract:
    """Machine-checkable shape inventory entry for one typed graph projection.

    The contract inventory is intentionally descriptive. It does not build a
    Neo4j projection, run GDS, emit findings, or create actions. Runtime
    builders should depend on these contracts only after a separate projection
    implementation patch exists.
    """

    name: str
    purpose: str
    input_facts: tuple[str, ...]
    node_types: tuple[str, ...]
    edge_types: tuple[str, ...]
    algorithm_families: tuple[AlgorithmFamily, ...]
    allowed_algorithms: tuple[str, ...]
    output_signals: tuple[str, ...]
    output_signal_families: tuple[SignalAlgorithmContract, ...]
    lineage_requirements: tuple[str, ...]
    sensitivity_rules: tuple[str, ...]
    forbidden_interpretations: tuple[str, ...]
    failure_modes: tuple[str, ...]
    status: str = "contract_only"
    contract_version: str = "v1"
    source_projections: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _clean_text(self.name, "name"))
        object.__setattr__(self, "purpose", _clean_text(self.purpose, "purpose"))
        object.__setattr__(self, "status", _clean_text(self.status, "status"))
        object.__setattr__(
            self,
            "contract_version",
            _clean_contract_version(self.contract_version),
        )
        object.__setattr__(
            self,
            "source_projections",
            _clean_optional_sequence(self.source_projections, "source_projections"),
        )
        object.__setattr__(
            self,
            "algorithm_families",
            _clean_algorithm_families(self.algorithm_families),
        )
        if not self.name.startswith("G_"):
            raise ValueError("projection contract name must start with G_")
        if self.name in self.source_projections:
            raise ValueError("projection contract cannot depend on itself")
        if self.status != "contract_only":
            raise ValueError("initial projection contracts must stay contract_only")
        for field_name in _REQUIRED_TEXT_SEQUENCE_FIELDS:
            object.__setattr__(
                self,
                field_name,
                _clean_sequence(getattr(self, field_name), field_name),
            )
        object.__setattr__(
            self,
            "output_signal_families",
            _clean_output_signal_families(
                self.output_signal_families,
                output_signals=self.output_signals,
                algorithm_families=self.algorithm_families,
            ),
        )


def _clean_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_name} must not be empty")
    return stripped


def _clean_contract_version(value: str) -> str:
    cleaned = _clean_text(value, "contract_version")
    if not cleaned.startswith("v") or not cleaned[1:].isdigit():
        raise ValueError("contract_version must use v<N> format")
    return cleaned


def _clean_sequence(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    if not values:
        raise ValueError(f"{field_name} must not be empty")
    return _clean_optional_sequence(values, field_name)


def _clean_optional_sequence(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    cleaned = tuple(_clean_text(value, field_name) for value in values)
    if len(cleaned) != len(set(cleaned)):
        raise ValueError(f"{field_name} must not contain duplicates")
    return cleaned


def _clean_algorithm_families(
    values: tuple[AlgorithmFamily | str, ...],
) -> tuple[AlgorithmFamily, ...]:
    if not values:
        raise ValueError("algorithm_families must not be empty")
    cleaned = tuple(AlgorithmFamily(value) for value in values)
    if len(cleaned) != len(set(cleaned)):
        raise ValueError("algorithm_families must not contain duplicates")
    return cleaned


def _clean_output_signal_families(
    values: tuple[SignalAlgorithmContract, ...],
    *,
    output_signals: tuple[str, ...],
    algorithm_families: tuple[AlgorithmFamily, ...],
) -> tuple[SignalAlgorithmContract, ...]:
    if not values:
        raise ValueError("output_signal_families must not be empty")
    cleaned = tuple(
        value if isinstance(value, SignalAlgorithmContract) else SignalAlgorithmContract(**value)
        for value in values
    )
    signal_names = tuple(value.signal_type for value in cleaned)
    if len(signal_names) != len(set(signal_names)):
        raise ValueError("output_signal_families must not contain duplicate signal types")
    missing = set(output_signals) - set(signal_names)
    extra = set(signal_names) - set(output_signals)
    if missing or extra:
        raise ValueError(
            "output_signal_families must exactly match output_signals "
            f"(missing={sorted(missing)}, extra={sorted(extra)})"
        )
    allowed_families = set(algorithm_families)
    for signal in cleaned:
        unknown = set(signal.algorithm_families) - allowed_families
        if unknown:
            raise ValueError(
                f"output signal {signal.signal_type} uses algorithm families outside the projection contract: "
                f"{sorted(family.value for family in unknown)}"
            )
    return cleaned


def _signal(
    signal_type: str,
    *algorithm_families: AlgorithmFamily,
) -> SignalAlgorithmContract:
    return SignalAlgorithmContract(signal_type=signal_type, algorithm_families=tuple(algorithm_families))


def _contract(
    *,
    name: str,
    purpose: str,
    input_facts: tuple[str, ...],
    node_types: tuple[str, ...],
    edge_types: tuple[str, ...],
    algorithm_families: tuple[AlgorithmFamily, ...],
    allowed_algorithms: tuple[str, ...],
    output_signals: tuple[str, ...],
    output_signal_families: tuple[SignalAlgorithmContract, ...],
    lineage_requirements: tuple[str, ...],
    sensitivity_rules: tuple[str, ...],
    forbidden_interpretations: tuple[str, ...],
    failure_modes: tuple[str, ...],
    source_projections: tuple[str, ...] = (),
    contract_version: str = "v1",
) -> ProjectionContract:
    return ProjectionContract(
        name=name,
        purpose=purpose,
        input_facts=input_facts,
        node_types=node_types,
        edge_types=edge_types,
        algorithm_families=algorithm_families,
        allowed_algorithms=allowed_algorithms,
        output_signals=output_signals,
        output_signal_families=output_signal_families,
        lineage_requirements=lineage_requirements,
        sensitivity_rules=sensitivity_rules,
        forbidden_interpretations=forbidden_interpretations,
        failure_modes=failure_modes,
        source_projections=source_projections,
        contract_version=contract_version,
    )
