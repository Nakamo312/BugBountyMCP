from __future__ import annotations

from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_graph_algorithm_backlog_documents_inventory_not_runtime_algorithms() -> None:
    backlog = _read("docs/architecture/graph-algorithm-backlog.md")

    assert "Status: inventory and ordering contract, no new runtime algorithms" in backlog
    assert "Do not add new GDS calls from this backlog patch" in backlog
    assert "PostgreSQL remains the source of truth" in backlog
    assert "Neo4j, GDS, and OpenSearch are rebuildable projections" in backlog


def test_graph_algorithm_backlog_captures_current_implemented_contours() -> None:
    backlog = _read("docs/architecture/graph-algorithm-backlog.md")

    expected_current = (
        "GraphFactBatchStore",
        "GraphFactBatchApplicator",
        "ActionOutcome <-> OutcomeFeature",
        "nodeSimilarity over outcome-feature neighborhoods",
        "SurfaceSnapshot",
        "SurfaceNode",
        "SurfaceDelta",
        "SurfaceFingerprint",
        "connected_components()",
        "component_profiles()",
        "component_bridges()",
        "component_outliers()",
        "component_coverage()",
        "component_drift()",
        "component_action_candidates()",
    )
    for token in expected_current:
        assert token in backlog


def test_graph_algorithm_backlog_lists_missing_typed_projection_contracts() -> None:
    backlog = _read("docs/architecture/graph-algorithm-backlog.md")

    for projection in (
        "G_asset",
        "G_http",
        "G_identity",
        "G_finding",
        "G_temporal",
        "G_bipartite_endpoint_param",
        "G_bipartite_host_tech",
        "G_bipartite_endpoint_object",
    ):
        assert f"### {projection}" in backlog

    required_contract_fields = (
        "node types",
        "edge types",
        "required facts",
        "purpose",
        "allowed algorithms",
        "output structural signals",
        "lineage requirements",
        "sensitivity rules",
        "forbidden interpretations",
    )
    for field in required_contract_fields:
        assert field in backlog


def test_graph_algorithm_backlog_keeps_vulnerability_labels_out_of_action_engine() -> None:
    backlog = _read("docs/architecture/graph-algorithm-backlog.md")

    assert "They are not graph action engines" in backlog
    assert "Signal is not finding" in backlog
    assert "Outputs are `PredictedRelationship` or `StructuralSignal`, not canonical facts" in backlog
    forbidden_recipes = (
        "param name contains id -> IDOR",
        "admin path -> admin action",
        "jwt observed -> JWT tamper run",
        "missing csrf token -> finding",
    )
    for recipe in forbidden_recipes:
        assert recipe in backlog


def test_graph_algorithm_backlog_orders_future_work_before_new_algorithms() -> None:
    backlog = _read("docs/architecture/graph-algorithm-backlog.md")

    expected_order = (
        "1. Typed projection contract inventory",
        "2. G_http minimal projection contract",
        "3. G_bipartite_endpoint_param baseline",
        "4. StructuralSignal event/read model",
        "5. Component coverage/drift scoring as deterministic metrics",
        "6. HypothesisProposal from StructuralSignal contract",
        "7. RAG/RLM task contracts over selected context",
        "8. Link prediction baseline over bipartite projections",
    )
    for step in expected_order:
        assert step in backlog

    assert backlog.index("1. Typed projection contract inventory") < backlog.index("8. Link prediction baseline")


def test_graph_algorithm_backlog_is_linked_from_navigation_docs() -> None:
    docs_index = _read("docs/README.md")
    readme = _read("README.md")
    agents = _read("AGENTS.md")
    handoff = _read("HANDOFF_FOR_NEW_CHAT.md")

    assert "architecture/graph-algorithm-backlog.md" in docs_index
    assert "docs/architecture/graph-algorithm-backlog.md" in readme
    assert "docs/architecture/graph-algorithm-backlog.md" in agents
    assert "docs/architecture/graph-algorithm-backlog.md" in handoff
