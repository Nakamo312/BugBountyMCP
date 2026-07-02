from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from api.application.program_projection_overview import (
    ExperienceProposalStatusSummary,
    LatestSurfaceSnapshotSummary,
    ProgramProjectionOverview,
    QueueStatusSummary,
    SearchIndexFreshnessSummary,
)
from api.application.workbench import (
    WorkbenchActionAffordance,
    WorkbenchActionAffordanceList,
    WorkbenchEdge,
    WorkbenchEntityMemory,
    WorkbenchGraph,
    WorkbenchLens,
    WorkbenchNode,
    WorkbenchReadService,
    WorkbenchRetrieveRequest,
    workbench_lenses,
    workbench_read_boundary,
)


class _OverviewService:
    def __init__(self, overview):
        self.overview_value = overview

    async def overview(self, *, program_id):
        return self.overview_value


class _GraphStore:
    def __init__(
        self,
        graph: WorkbenchGraph | None = None,
        actions: WorkbenchActionAffordanceList | None = None,
        memory: WorkbenchEntityMemory | None = None,
    ) -> None:
        self.graph = graph
        self.actions = actions
        self.memory = memory
        self.calls: list[dict[str, object]] = []

    async def surface_graph(self, **kwargs):
        self.calls.append({"method": "surface_graph", **kwargs})
        return self.graph

    async def component_graph(self, **kwargs):
        self.calls.append({"method": "component_graph", **kwargs})
        return self.graph

    async def memory_graph(self, **kwargs):
        self.calls.append({"method": "memory_graph", **kwargs})
        return self.graph

    async def action_graph(self, **kwargs):
        self.calls.append({"method": "action_graph", **kwargs})
        return self.graph

    async def hypothesis_graph(self, **kwargs):
        self.calls.append({"method": "hypothesis_graph", **kwargs})
        return self.graph

    async def coverage_graph(self, **kwargs):
        self.calls.append({"method": "coverage_graph", **kwargs})
        return self.graph

    async def neo4j_graph(self, **kwargs):
        self.calls.append({"method": "neo4j_graph", **kwargs})
        return self.graph

    async def entity_profile(self, **kwargs):
        self.calls.append({"method": "entity_profile", **kwargs})
        return None

    async def entity_actions(self, **kwargs):
        self.calls.append({"method": "entity_actions", **kwargs})
        return self.actions

    async def entity_memory(self, **kwargs):
        self.calls.append({"method": "entity_memory", **kwargs})
        return self.memory


def _overview(program_id: UUID) -> ProgramProjectionOverview:
    snapshot_id = uuid4()
    return ProgramProjectionOverview(
        program_id=program_id,
        latest_surface_snapshot=LatestSurfaceSnapshotSummary(
            snapshot_id=snapshot_id,
            snapshot_fingerprint="f" * 64,
            algorithm="surface-map",
            algorithm_version="surface-map-v1",
            node_count=11,
            edge_count=7,
            delta_count=3,
            created_at=datetime(2026, 6, 30, tzinfo=timezone.utc),
        ),
        latest_surface_analysis=None,
        surface_analysis_fresh=True,
        search_index_fresh=False,
        ui_data_fresh=False,
        graph_projection_events=QueueStatusSummary(pending=1),
        graph_fact_batches=QueueStatusSummary(locked=1),
        surface_analysis_events=QueueStatusSummary(),
        search_projection_events=QueueStatusSummary(failed=1),
        search_index=SearchIndexFreshnessSummary(surface_components_indexed=False, surface_deltas_indexed=False),
        experience_proposals=ExperienceProposalStatusSummary(pending=2),
        boundary={"gds_execution": "forbidden"},
    )


def test_workbench_lenses_expose_surface_now_and_future_lens_contracts() -> None:
    lenses = workbench_lenses()

    assert [lens.lens for lens in lenses] == [
        WorkbenchLens.SURFACE,
        WorkbenchLens.COMPONENTS,
        WorkbenchLens.MEMORY,
        WorkbenchLens.HYPOTHESIS,
        WorkbenchLens.ACTION,
        WorkbenchLens.COVERAGE,
        WorkbenchLens.NEO4J_EXPOSURE,
        WorkbenchLens.NEO4J_ENDPOINT,
        WorkbenchLens.NEO4J_EVIDENCE,
        WorkbenchLens.NEO4J_SURFACE_MATH,
        WorkbenchLens.NEO4J_ACTION_OUTCOME,
        WorkbenchLens.NEO4J_JS,
        WorkbenchLens.NEO4J_TECH,
        WorkbenchLens.NEO4J_HYPOTHESIS,
    ]
    assert lenses[0].available is True
    assert lenses[0].default is True
    assert lenses[1].available is False
    assert lenses[1].reason == "no_materialized_surface_component_analysis"
    assert lenses[2].lens == WorkbenchLens.MEMORY
    assert lenses[2].available is True
    assert lenses[2].reason is None
    assert lenses[3].lens == WorkbenchLens.HYPOTHESIS
    assert lenses[3].available is True
    assert lenses[3].reason is None
    assert lenses[4].available is True
    assert lenses[4].reason is None
    assert lenses[5].available is False
    assert lenses[5].reason == "no_surface_snapshot"


def test_workbench_lenses_enable_components_when_materialized_analysis_exists() -> None:
    program_id = uuid4()
    lenses = workbench_lenses(_overview(program_id).model_copy(update={
        "latest_surface_analysis": {
            "analysis_run_id": uuid4(),
            "snapshot_id": uuid4(),
            "report_fingerprint": "a" * 64,
            "algorithm": "surface-component-report",
            "algorithm_version": "surface-component-analysis-v1",
            "item_count": 3,
            "created_at": datetime(2026, 6, 30, tzinfo=timezone.utc),
        }
    }))

    components = lenses[1]
    assert components.lens == WorkbenchLens.COMPONENTS
    assert components.available is True
    assert components.reason is None
    coverage = lenses[5]
    assert coverage.lens == WorkbenchLens.COVERAGE
    assert coverage.available is True
    assert coverage.reason is None


def test_workbench_boundary_blocks_execution_and_raw_database_surfaces() -> None:
    boundary = workbench_read_boundary(surface="surface_lens_graph")

    assert boundary["postgres_write"] == "forbidden"
    assert boundary["neo4j_read"] == "forbidden"
    assert boundary["raw_cypher"] == "forbidden"
    assert boundary["gds_execution"] == "forbidden"
    assert boundary["proposal_creation"] == "forbidden"
    assert boundary["action_submission"] == "forbidden"
    assert boundary["tool_execution"] == "forbidden"
    assert boundary["raw_secret_material"] == "forbidden"


@pytest.mark.asyncio
async def test_workbench_bootstrap_maps_projection_overview_without_raw_db_shape() -> None:
    program_id = uuid4()
    service = WorkbenchReadService(
        graph_store=_GraphStore(),
        projection_overview=_OverviewService(_overview(program_id)),
    )

    bootstrap = await service.bootstrap(program_id=program_id)

    assert bootstrap.program_id == program_id
    assert bootstrap.selected_lens == WorkbenchLens.SURFACE
    assert bootstrap.projection_freshness["surface_analysis_fresh"] is True
    assert bootstrap.queue_health["graph_projection_events"]["pending"] == 1
    assert bootstrap.counts == {
        "surface_nodes": 11,
        "surface_edges": 7,
        "surface_deltas": 3,
        "experience_proposals_pending": 2,
    }
    assert bootstrap.boundary["raw_cypher"] == "forbidden"


@pytest.mark.asyncio
async def test_surface_graph_request_is_clamped_and_delegated_to_store() -> None:
    program_id = uuid4()
    graph = WorkbenchGraph(
        program_id=program_id,
        lens=WorkbenchLens.SURFACE,
        nodes=[WorkbenchNode(id="node:1", entity_key="surface:endpoint:f", node_type="endpoint", label="GET /")],
    )
    store = _GraphStore(graph)
    service = WorkbenchReadService(
        graph_store=store,
        projection_overview=_OverviewService(_overview(program_id)),
    )

    result = await service.graph(program_id=program_id, depth=99, limit=999)

    assert result is graph
    assert store.calls == [
        {"method": "surface_graph", "program_id": program_id, "seed": None, "depth": 4, "limit": 500}
    ]


@pytest.mark.asyncio
async def test_component_lens_delegates_to_materialized_component_graph_store() -> None:
    program_id = uuid4()
    graph = WorkbenchGraph(program_id=program_id, lens=WorkbenchLens.COMPONENTS)
    store = _GraphStore(graph)
    service = WorkbenchReadService(
        graph_store=store,
        projection_overview=_OverviewService(_overview(program_id)),
    )

    result = await service.graph(program_id=program_id, lens=WorkbenchLens.COMPONENTS, depth=99, limit=999)

    assert result is graph
    assert store.calls == [
        {"method": "component_graph", "program_id": program_id, "seed": None, "depth": 4, "limit": 500}
    ]


@pytest.mark.asyncio
async def test_memory_lens_delegates_to_action_outcome_memory_graph_store() -> None:
    program_id = uuid4()
    graph = WorkbenchGraph(program_id=program_id, lens=WorkbenchLens.MEMORY)
    store = _GraphStore(graph)
    service = WorkbenchReadService(
        graph_store=store,
        projection_overview=_OverviewService(_overview(program_id)),
    )

    result = await service.graph(program_id=program_id, lens=WorkbenchLens.MEMORY, depth=99, limit=999)

    assert result is graph
    assert store.calls == [
        {"method": "memory_graph", "program_id": program_id, "seed": None, "depth": 4, "limit": 500}
    ]


@pytest.mark.asyncio
async def test_action_lens_delegates_to_action_lifecycle_graph_store() -> None:
    program_id = uuid4()
    graph = WorkbenchGraph(program_id=program_id, lens=WorkbenchLens.ACTION)
    store = _GraphStore(graph)
    service = WorkbenchReadService(
        graph_store=store,
        projection_overview=_OverviewService(_overview(program_id)),
    )

    result = await service.graph(program_id=program_id, lens=WorkbenchLens.ACTION, depth=99, limit=999)

    assert result is graph
    assert store.calls == [
        {"method": "action_graph", "program_id": program_id, "seed": None, "depth": 4, "limit": 500}
    ]


@pytest.mark.asyncio
async def test_coverage_lens_delegates_to_structural_coverage_graph_store() -> None:
    program_id = uuid4()
    graph = WorkbenchGraph(program_id=program_id, lens=WorkbenchLens.COVERAGE)
    store = _GraphStore(graph)
    service = WorkbenchReadService(
        graph_store=store,
        projection_overview=_OverviewService(_overview(program_id)),
    )

    result = await service.graph(program_id=program_id, lens=WorkbenchLens.COVERAGE, depth=99, limit=999)

    assert result is graph
    assert store.calls == [
        {"method": "coverage_graph", "program_id": program_id, "seed": None, "depth": 4, "limit": 500}
    ]


@pytest.mark.asyncio
async def test_hypothesis_lens_delegates_to_reasoning_graph_store() -> None:
    program_id = uuid4()
    graph = WorkbenchGraph(program_id=program_id, lens=WorkbenchLens.HYPOTHESIS)
    store = _GraphStore(graph)
    service = WorkbenchReadService(
        graph_store=store,
        projection_overview=_OverviewService(_overview(program_id)),
    )

    result = await service.graph(program_id=program_id, lens=WorkbenchLens.HYPOTHESIS, depth=99, limit=999)

    assert result is graph
    assert store.calls == [
        {"method": "hypothesis_graph", "program_id": program_id, "seed": None, "depth": 4, "limit": 500}
    ]


@pytest.mark.asyncio
async def test_entity_actions_are_delegated_to_read_store_not_stubbed() -> None:
    program_id = uuid4()
    actions = WorkbenchActionAffordanceList(
        program_id=program_id,
        entity_key="surface:endpoint:f",
        actions=[
            WorkbenchActionAffordance(
                catalog_id="httpx.discovery",
                label="httpx.discovery / safe_recon",
                profile="safe_recon",
                enabled=True,
            )
        ],
    )
    store = _GraphStore(actions=actions)
    service = WorkbenchReadService(graph_store=store, projection_overview=_OverviewService(_overview(program_id)))

    result = await service.entity_actions(program_id=program_id, entity_key="surface:endpoint:f")

    assert result is actions
    assert store.calls == [
        {"method": "entity_actions", "program_id": program_id, "entity_key": "surface:endpoint:f"}
    ]


@pytest.mark.asyncio
async def test_retrieve_assembles_evidence_pack_from_entity_memory() -> None:
    program_id = uuid4()
    graph = WorkbenchGraph(program_id=program_id, lens=WorkbenchLens.SURFACE)
    memory = WorkbenchEntityMemory(
        program_id=program_id,
        entity_key="surface:endpoint:f",
        fragments=[{"kind": "action_outcome", "id": "outcome-1"}],
        evidence_refs=[{"type": "action_outcome", "id": "outcome-1"}],
    )
    store = _GraphStore(graph=graph, memory=memory)
    service = WorkbenchReadService(graph_store=store, projection_overview=_OverviewService(_overview(program_id)))

    result = await service.retrieve(
        request=WorkbenchRetrieveRequest(program_id=program_id, selected_entities=["surface:endpoint:f"])
    )

    assert result.boundary["surface"] == "hybrid_retrieval_evidence_pack"
    assert result.fragments == [{"entity_key": "surface:endpoint:f", "kind": "action_outcome", "id": "outcome-1"}]
    assert result.evidence_refs == [{"type": "action_outcome", "id": "outcome-1"}]


def test_workbench_route_is_registered() -> None:
    source = Path("src/api/presentation/rest/routes/__init__.py").read_text(encoding="utf-8")

    assert "workbench_router" in source
    assert "/api/v1/workbench" in source


def test_workbench_routes_expose_required_read_contracts() -> None:
    source = Path("src/api/presentation/rest/routes/workbench.py").read_text(encoding="utf-8")

    assert '"/bootstrap"' in source
    assert '"/graph"' in source
    assert '"/entities/{entity_key}"' in source
    assert '"/entities/{entity_key}/actions"' in source
    assert '"/entities/{entity_key}/memory"' in source
    assert '"/retrieve"' in source


@pytest.mark.asyncio
async def test_retrieve_applies_temporal_scope_graph_summary_ranking_and_redaction() -> None:
    program_id = uuid4()
    selected = "surface:endpoint:f"
    neighbor = "surface:host:h"
    graph = WorkbenchGraph(
        program_id=program_id,
        lens=WorkbenchLens.SURFACE,
        seed=selected,
        nodes=[
            WorkbenchNode(id="node:1", entity_key=selected, node_type="endpoint", label="GET /api/users"),
            WorkbenchNode(id="node:2", entity_key=neighbor, node_type="host", label="example.com"),
        ],
        edges=[
            WorkbenchEdge(
                id="edge:1",
                source="node:1",
                target="node:2",
                relationship_type="BELONGS_TO_HOST",
                label="belongs to host",
                source_projection="surface_map",
            )
        ],
    )
    memory = WorkbenchEntityMemory(
        program_id=program_id,
        entity_key=selected,
        fragments=[
            {
                "kind": "action_outcome",
                "outcome_id": "outcome-new",
                "run_id": "run-new",
                "created_at": "2026-06-30T10:00:00+00:00",
                "capability_id": "katana",
                "delta": {"surface_nodes": 5, "search_documents": 2},
                "score": {"information_gain": 8},
                "note": "endpoint expansion",
            },
            {
                "kind": "action_outcome",
                "outcome_id": "outcome-old",
                "run_id": "run-old",
                "created_at": "2026-01-01T10:00:00+00:00",
                "delta": {"surface_nodes": 99, "search_documents": 3},
            },
        ],
        evidence_refs=[{"type": "action_outcome", "id": "outcome-new"}],
    )
    store = _GraphStore(graph=graph, memory=memory)
    service = WorkbenchReadService(graph_store=store, projection_overview=_OverviewService(_overview(program_id)))

    result = await service.retrieve(
        request=WorkbenchRetrieveRequest(
            program_id=program_id,
            selected_entities=[selected, selected],
            query="Authorization: Bearer should-redact endpoint expansion",
            temporal_scope={"since": "2026-06-01T00:00:00+00:00"},
            lens=WorkbenchLens.SURFACE,
        )
    )

    assert result.selected_entities == [selected]
    assert "should-redact" not in str(result.model_dump(mode="json"))
    assert result.query == "Authorization: Bearer [redacted] endpoint expansion"
    assert "endpoint" in result.query_terms
    assert result.temporal_scope["applied"] is True
    assert [fragment["outcome_id"] for fragment in result.fragments] == ["outcome-new"]
    assert result.ranked_context[0]["reasons"] == [
        "selected_entity_memory",
        "query_term_match",
        "selected_entity_exact",
        "delta_signal",
        "information_gain",
        "evidence_ref",
    ]
    assert result.search_projection_refs == [
        {"type": "search_projection_delta", "run_id": "run-new", "new_search_documents_count": 2}
    ]
    assert result.graph_context_summary["available"] is True
    assert result.graph_context_summary["neighbor_count"] == 1
    assert result.boundary["prompt_blob"] == "forbidden"
    assert result.boundary["opensearch_lookup"] == "not_performed"


def test_workbench_read_service_delegates_retrieve_assembly_instead_of_importing_private_helpers() -> None:
    service_source = Path("src/api/application/workbench.py").read_text(encoding="utf-8")
    retrieve_source = Path("src/api/application/workbench_retrieve.py").read_text(encoding="utf-8")

    assert "assemble_evidence_pack_payload" in service_source
    assert "from api.application.workbench_retrieve import (" not in service_source
    assert "_rank_context_fragments" not in service_source
    assert "_redact_text" not in service_source
    assert "_temporal_scope" not in service_source
    assert "async def assemble_evidence_pack_payload" in retrieve_source


def test_workbench_projection_control_contract_is_allowlisted_not_command_text() -> None:
    source = Path("src/api/application/workbench_projection_control.py").read_text(encoding="utf-8")
    route = Path("src/api/presentation/rest/routes/workbench.py").read_text(encoding="utf-8")
    infra = Path("src/api/infrastructure/workbench_projection_control.py").read_text(encoding="utf-8")

    assert "class WorkbenchProjectionOperation" in source
    assert "BUILD_SURFACE" in source
    assert "MATERIALIZE_COMPONENTS" in source
    assert "REFRESH_WORKBENCH" in source
    assert "user_supplied_command_text" in source
    assert "arbitrary_command_execution" in source
    assert '"/projections/run"' in route
    assert "WorkbenchProjectionRunRequest" in route
    assert "subprocess.run" in infra
    assert "shell=True" not in infra
    assert "request.command" not in infra
    assert "surface_engine" in infra
    assert "graph_projector" in infra


@pytest.mark.asyncio
async def test_neo4j_lenses_delegate_to_allowlisted_graph_projector_templates() -> None:
    program_id = uuid4()
    graph = WorkbenchGraph(program_id=program_id, lens=WorkbenchLens.NEO4J_EXPOSURE)
    store = _GraphStore(graph)
    service = WorkbenchReadService(
        graph_store=store,
        projection_overview=_OverviewService(_overview(program_id)),
    )

    result = await service.graph(program_id=program_id, lens=WorkbenchLens.NEO4J_EXPOSURE, depth=99, limit=999)

    assert result is graph
    assert store.calls == [
        {
            "method": "neo4j_graph",
            "program_id": program_id,
            "lens": WorkbenchLens.NEO4J_EXPOSURE,
            "seed": None,
            "depth": 4,
            "limit": 500,
        }
    ]


def test_workbench_exposes_neo4j_lenses_without_raw_cypher_or_gds_execution() -> None:
    lenses = workbench_lenses(_overview(uuid4()))
    neo4j_lenses = [lens for lens in lenses if lens.lens.value.startswith("neo4j_")]

    assert [lens.lens for lens in neo4j_lenses] == [
        WorkbenchLens.NEO4J_EXPOSURE,
        WorkbenchLens.NEO4J_ENDPOINT,
        WorkbenchLens.NEO4J_EVIDENCE,
        WorkbenchLens.NEO4J_SURFACE_MATH,
        WorkbenchLens.NEO4J_ACTION_OUTCOME,
        WorkbenchLens.NEO4J_JS,
        WorkbenchLens.NEO4J_TECH,
        WorkbenchLens.NEO4J_HYPOTHESIS,
    ]
    assert all(lens.available for lens in neo4j_lenses)
    assert workbench_read_boundary(surface="surface")["raw_cypher"] == "forbidden"
    assert workbench_read_boundary(surface="surface")["neo4j_write"] == "forbidden"

from api.application.action_catalog import CatalogDetail, CatalogItem
from api.application.execution_limits import ExecutionBudget
from api.application.workbench import WorkbenchEntityProfile
from api.application.workbench_action_affordances import (
    WorkbenchActionAffordanceService,
    WorkbenchAvailableActionsRequest,
)


class _AffordanceWorkbench:
    def __init__(self, profile: WorkbenchEntityProfile) -> None:
        self.profile = profile

    async def entity_profile(self, *, program_id, entity_key):
        return self.profile


class _AffordanceCatalog:
    def __init__(self, detail: CatalogDetail) -> None:
        self.detail = detail

    async def list_items(self):
        return [
            CatalogItem(
                id=self.detail.id,
                capability=self.detail.capability,
                profile=self.detail.profile,
                capability_label=self.detail.capability_label,
                profile_label=self.detail.profile_label,
                safety_level=self.detail.safety_level,
                requires_approval=self.detail.requires_approval,
            )
        ]

    async def get_detail(self, item_id):
        assert item_id == self.detail.id
        return self.detail


class _NoopActionService:
    pass


@pytest.mark.asyncio
async def test_workbench_action_affordances_are_derived_from_catalog_target_contracts() -> None:
    program_id = uuid4()
    catalog_id = uuid4()
    detail = CatalogDetail(
        id=catalog_id,
        snapshot_id=uuid4(),
        capability="naabu",
        profile="passive-ports",
        capability_label="Naabu",
        profile_label="Passive port discovery",
        safety_level="passive",
        requires_approval=False,
        queue="analysis",
        request_event="naabu_scan_requested",
        default_profile="passive-ports",
        scope_policy="strict",
        execution_budget=ExecutionBudget(max_targets=100),
        frontend={
            "workbench": {
                "produces": ["Service", "Observation", "Artifact"],
                "target_contracts": [
                    {
                        "kind": "host-or-ip",
                        "labels": ["IP", "Host"],
                        "required_any_properties": ["address", "hostname"],
                        "target_property": "address",
                        "reason": "IP can seed port discovery.",
                    }
                ],
            }
        },
        submit={},
    )
    profile = WorkbenchEntityProfile(
        program_id=program_id,
        entity_key="neo4j:IP:ip%3A1.2.3.4",
        profile={"labels": ["IP"], "label": "1.2.3.4", "projection_source": "neo4j"},
        properties={"address": "1.2.3.4"},
    )
    service = WorkbenchActionAffordanceService(
        workbench=_AffordanceWorkbench(profile),
        catalog=_AffordanceCatalog(detail),
        actions=_NoopActionService(),
    )

    result = await service.available(
        WorkbenchAvailableActionsRequest(program_id=program_id, entity_key=profile.entity_key)
    )

    assert result.actions[0].catalog_id == str(catalog_id)
    assert result.actions[0].tool == "naabu"
    assert result.actions[0].inputs == {"targets": ["1.2.3.4"], "target": "1.2.3.4"}
    assert result.actions[0].enabled is True
    assert result.actions[0].policy_preview["scope_policy"] == "strict"
    assert result.boundary["raw_frontend_tool_rules"] == "forbidden"
