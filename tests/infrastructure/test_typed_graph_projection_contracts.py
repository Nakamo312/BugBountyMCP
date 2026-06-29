from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path("services/graph-projector").resolve()))

from graph_projector.projection_contracts import (  # noqa: E402
    EXPECTED_PROJECTION_CONTRACT_NAMES,
    PROJECTION_CONTRACT_NAMES,
    PROJECTION_CONTRACTS,
    PROJECTION_CONTRACTS_BY_NAME,
    AlgorithmFamily,
    ProjectionContract,
    SignalAlgorithmContract,
    validate_projection_contract_inventory,
    get_projection_contract,
    projection_contract_names,
)


REQUIRED_PROJECTION_NAMES = (
    "G_asset",
    "G_http",
    "G_identity",
    "G_finding",
    "G_temporal",
    "G_bipartite_endpoint_param",
    "G_bipartite_host_tech",
    "G_bipartite_endpoint_object",
)


REQUIRED_SEQUENCE_FIELDS = (
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


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_projection_contract_inventory_has_exact_required_projection_spaces() -> None:
    assert EXPECTED_PROJECTION_CONTRACT_NAMES == REQUIRED_PROJECTION_NAMES
    assert PROJECTION_CONTRACT_NAMES == REQUIRED_PROJECTION_NAMES
    assert projection_contract_names() == REQUIRED_PROJECTION_NAMES
    assert tuple(PROJECTION_CONTRACTS_BY_NAME) == REQUIRED_PROJECTION_NAMES
    assert tuple(contract.name for contract in PROJECTION_CONTRACTS) == REQUIRED_PROJECTION_NAMES


def test_projection_contracts_are_machine_checkable_shape_inventory_entries() -> None:
    for contract in PROJECTION_CONTRACTS:
        assert isinstance(contract, ProjectionContract)
        assert contract.name.startswith("G_")
        assert contract.contract_version == "v1"
        assert contract.purpose
        assert contract.status == "contract_only"
        assert isinstance(contract.source_projections, tuple)
        assert all(source in PROJECTION_CONTRACTS_BY_NAME for source in contract.source_projections)
        assert isinstance(contract.algorithm_families, tuple)
        assert contract.algorithm_families
        assert all(isinstance(family, AlgorithmFamily) for family in contract.algorithm_families)
        assert len(contract.algorithm_families) == len(set(contract.algorithm_families))
        assert {signal.signal_type for signal in contract.output_signal_families} == set(contract.output_signals)
        for signal in contract.output_signal_families:
            assert set(signal.algorithm_families).issubset(set(contract.algorithm_families))
        for field_name in REQUIRED_SEQUENCE_FIELDS:
            values = getattr(contract, field_name)
            assert isinstance(values, tuple), field_name
            assert values, field_name
            assert all(isinstance(value, str) and value.strip() for value in values), field_name
            assert len(values) == len(set(values)), field_name


def test_projection_contract_constructor_rejects_incomplete_contracts() -> None:
    try:
        ProjectionContract(
            name="G_bad",
            purpose="bad contract",
            input_facts=(),
            node_types=("node",),
            edge_types=("EDGE",),
            algorithm_families=(AlgorithmFamily.DEGREE,),
            allowed_algorithms=("degree",),
            output_signals=("Signal",),
            output_signal_families=(SignalAlgorithmContract("Signal", (AlgorithmFamily.DEGREE,)),),
            lineage_requirements=("program_id",),
            sensitivity_rules=("redact secrets",),
            forbidden_interpretations=("not a finding",),
            failure_modes=("bad input",),
        )
    except ValueError as exc:
        assert "input_facts" in str(exc)
    else:  # pragma: no cover - defensive clarity for this policy test
        raise AssertionError("ProjectionContract accepted an empty input_facts field")


def test_projection_contract_constructor_rejects_bad_version_and_algorithm_family() -> None:
    base_kwargs = dict(
        name="G_bad",
        purpose="bad contract",
        input_facts=("fact",),
        node_types=("node",),
        edge_types=("EDGE",),
        algorithm_families=(AlgorithmFamily.DEGREE,),
        allowed_algorithms=("degree",),
        output_signals=("Signal",),
        output_signal_families=(SignalAlgorithmContract("Signal", (AlgorithmFamily.DEGREE,)),),
        lineage_requirements=("program_id",),
        sensitivity_rules=("redact secrets",),
        forbidden_interpretations=("not a finding",),
        failure_modes=("bad input",),
    )
    try:
        ProjectionContract(**base_kwargs, contract_version="1")
    except ValueError as exc:
        assert "contract_version" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("ProjectionContract accepted an unversioned contract")

    bad_family_kwargs = {**base_kwargs, "algorithm_families": ("made_up_family",)}
    try:
        ProjectionContract(**bad_family_kwargs)
    except ValueError as exc:
        assert "made_up_family" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("ProjectionContract accepted an unknown algorithm family")


def test_projection_contracts_reject_self_dependency_and_dependency_cycles() -> None:
    base_kwargs = dict(
        purpose="test dependency graph",
        input_facts=("fact",),
        node_types=("node",),
        edge_types=("EDGE",),
        algorithm_families=(AlgorithmFamily.DEGREE,),
        allowed_algorithms=("degree",),
        output_signals=("Signal",),
        output_signal_families=(SignalAlgorithmContract("Signal", (AlgorithmFamily.DEGREE,)),),
        lineage_requirements=("program_id",),
        sensitivity_rules=("redact secrets",),
        forbidden_interpretations=("not a finding",),
        failure_modes=("bad input",),
    )
    try:
        ProjectionContract(name="G_self", source_projections=("G_self",), **base_kwargs)
    except ValueError as exc:
        assert "depend on itself" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("ProjectionContract accepted a self dependency")

    first = ProjectionContract(name="G_first", source_projections=("G_second",), **base_kwargs)
    second = ProjectionContract(name="G_second", source_projections=("G_first",), **base_kwargs)
    try:
        validate_projection_contract_inventory((first, second))
    except ValueError as exc:
        assert "dependency cycle" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("projection inventory accepted a dependency cycle")


def test_projection_contracts_reject_signal_algorithm_family_drift() -> None:
    base_kwargs = dict(
        name="G_signal_bad",
        purpose="bad signal mapping",
        input_facts=("fact",),
        node_types=("node",),
        edge_types=("EDGE",),
        algorithm_families=(AlgorithmFamily.DEGREE,),
        allowed_algorithms=("degree",),
        output_signals=("Signal",),
        lineage_requirements=("program_id",),
        sensitivity_rules=("redact secrets",),
        forbidden_interpretations=("not a finding",),
        failure_modes=("bad input",),
    )
    try:
        ProjectionContract(
            **base_kwargs,
            output_signal_families=(SignalAlgorithmContract("OtherSignal", (AlgorithmFamily.DEGREE,)),),
        )
    except ValueError as exc:
        assert "output_signal_families" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("ProjectionContract accepted a signal mapping with unknown output signal")

    try:
        ProjectionContract(
            **base_kwargs,
            output_signal_families=(SignalAlgorithmContract("Signal", (AlgorithmFamily.DRIFT_SUMMARY,)),),
        )
    except ValueError as exc:
        assert "outside the projection contract" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("ProjectionContract accepted a signal algorithm outside contract families")


def test_bipartite_projection_dependencies_reference_existing_projection_contracts() -> None:
    assert get_projection_contract("G_bipartite_endpoint_param").source_projections == ("G_http",)
    assert get_projection_contract("G_bipartite_host_tech").source_projections == ("G_asset",)
    assert get_projection_contract("G_bipartite_endpoint_object").source_projections == ("G_http",)


def test_g_http_contract_contains_expected_http_surface_space() -> None:
    contract = get_projection_contract("G_http")

    for node_type in (
        "endpoint",
        "route_template",
        "method",
        "param",
        "response_shape",
        "status_class",
        "content_type",
        "observed_action",
    ):
        assert node_type in contract.node_types

    assert contract.contract_version == "v1"
    assert AlgorithmFamily.DEGREE in contract.algorithm_families
    assert AlgorithmFamily.JACCARD_SIMILARITY in contract.algorithm_families
    assert AlgorithmFamily.DRIFT_SUMMARY in contract.algorithm_families
    assert "HAS_PARAM" in contract.edge_types
    assert "endpoint similarity by parameter neighborhood" in contract.allowed_algorithms
    assert "HttpMissingRelationCandidateSignal" in contract.output_signals
    assert any("raw headers" in rule for rule in contract.sensitivity_rules)


def test_projection_contracts_keep_structural_signals_separate_from_findings_and_actions() -> None:
    for contract in PROJECTION_CONTRACTS:
        forbidden_text = "\n".join(contract.forbidden_interpretations).lower()
        assert "not" in forbidden_text
        assert any(keyword in forbidden_text for keyword in ("finding", "verdict", "permission", "action", "proof"))
        assert all("action engine" not in signal.lower() for signal in contract.output_signals)

    g_http_forbidden = "\n".join(get_projection_contract("G_http").forbidden_interpretations)
    assert "parameter names are not IDOR findings" in g_http_forbidden
    assert "JWT observations are not JWT-tamper action engines" in g_http_forbidden
    assert "missing CSRF-like observations are not findings" in g_http_forbidden


def test_projection_contracts_are_linked_from_human_docs() -> None:
    typed_doc = _read("docs/architecture/typed-graph-projections.md")
    docs_index = _read("docs/README.md")
    readme = _read("README.md")
    agents = _read("AGENTS.md")
    handoff = _read("HANDOFF_FOR_NEW_CHAT.md")

    assert "services/graph-projector/graph_projector/projection_contracts.py" in typed_doc
    assert "machine-checkable shape inventory" in typed_doc
    assert "contract_version" in typed_doc
    assert "source_projections" in typed_doc
    assert "AlgorithmFamily" in typed_doc
    for projection_name in REQUIRED_PROJECTION_NAMES:
        assert projection_name in typed_doc

    assert "architecture/typed-graph-projections.md" in docs_index
    assert "docs/architecture/typed-graph-projections.md" in readme
    assert "docs/architecture/typed-graph-projections.md" in agents
    assert "docs/architecture/typed-graph-projections.md" in handoff


def test_graph_backlog_points_to_machine_checked_projection_contracts() -> None:
    backlog = _read("docs/architecture/graph-algorithm-backlog.md")

    assert "Typed projection contract inventory" in backlog
    assert "projection_contracts.py" in backlog
    assert "ProjectionContract" in backlog
    assert "contract source of truth" in backlog
    assert "contract_version" in backlog
    assert "source_projections" in backlog
