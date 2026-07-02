"""Read-side contract for the dashboard workbench.

The workbench is a UI-oriented read boundary over existing projections. It does
not execute tools, create proposals, run GDS, submit actions, write Cypher, or
let the frontend reconstruct product semantics from raw database rows.
"""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from api.application.workbench_retrieve import assemble_evidence_pack_payload

from api.application.program_projection_overview import (
    ProgramProjectionOverview,
    ProgramProjectionOverviewNotFound,
    ProgramProjectionOverviewService,
)


class WorkbenchNotFound(Exception):
    """Raised when the workbench cannot resolve requested read-side state."""


class WorkbenchLens(StrEnum):
    SURFACE = "surface"
    COMPONENTS = "components"
    MEMORY = "memory"
    HYPOTHESIS = "hypothesis"
    ACTION = "action"
    COVERAGE = "coverage"
    NEO4J_EXPOSURE = "neo4j_exposure"
    NEO4J_ENDPOINT = "neo4j_endpoint"
    NEO4J_EVIDENCE = "neo4j_evidence"
    NEO4J_SURFACE_MATH = "neo4j_surface_math"
    NEO4J_ACTION_OUTCOME = "neo4j_action_outcome"
    NEO4J_JS = "neo4j_js"
    NEO4J_TECH = "neo4j_tech"
    NEO4J_HYPOTHESIS = "neo4j_hypothesis"


class WorkbenchNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    entity_key: str
    node_type: str
    label: str
    caption: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    visual: dict[str, Any] = Field(default_factory=dict)
    badges: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    action_affordance_count: int = 0
    staleness: str = "unknown"
    confidence: float = 0.0
    source_refs: list[dict[str, Any]] = Field(default_factory=list)


class WorkbenchEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    source: str
    target: str
    relationship_type: str
    label: str
    caption: str | None = None
    weight: float = 1.0
    confidence: float = 1.0
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime | None = None
    last_seen_at: datetime | None = None
    delta_state: str = "unknown"
    source_projection: str = "surface_map"


class WorkbenchGraph(BaseModel):
    model_config = ConfigDict(extra="forbid")

    program_id: UUID
    lens: WorkbenchLens
    snapshot_id: UUID | None = None
    seed: str | None = None
    depth: int = 1
    nodes: list[WorkbenchNode] = Field(default_factory=list)
    edges: list[WorkbenchEdge] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
    boundary: dict[str, Any] = Field(default_factory=dict)


class WorkbenchLensDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lens: WorkbenchLens
    label: str
    available: bool
    default: bool = False
    reason: str | None = None


class WorkbenchBootstrap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    program_id: UUID
    selected_lens: WorkbenchLens = WorkbenchLens.SURFACE
    lenses: list[WorkbenchLensDescriptor]
    projection_freshness: dict[str, Any] = Field(default_factory=dict)
    queue_health: dict[str, Any] = Field(default_factory=dict)
    counts: dict[str, int] = Field(default_factory=dict)
    default_graph_seed: str | None = None
    boundary: dict[str, Any] = Field(default_factory=dict)


class WorkbenchEntityProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    program_id: UUID
    entity_key: str
    profile: dict[str, Any] = Field(default_factory=dict)
    properties: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    related_hypotheses: list[dict[str, Any]] = Field(default_factory=list)
    related_outcomes: list[dict[str, Any]] = Field(default_factory=list)
    related_actions: list[dict[str, Any]] = Field(default_factory=list)
    memory_pointers: list[dict[str, Any]] = Field(default_factory=list)
    boundary: dict[str, Any] = Field(default_factory=dict)


class WorkbenchActionAffordance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    catalog_id: str
    label: str
    profile: str
    required_inputs: list[dict[str, Any]] = Field(default_factory=list)
    prefilled_options: dict[str, Any] = Field(default_factory=dict)
    enabled: bool
    disabled_reasons: list[str] = Field(default_factory=list)
    tool: str | None = None
    state: str = "unknown"
    approval_required: bool = False
    risk_class: str | None = None
    reason: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    submit_payload: dict[str, Any] = Field(default_factory=dict)
    policy_preview: dict[str, Any] = Field(default_factory=dict)
    budget_preview: dict[str, Any] = Field(default_factory=dict)
    expected_delta: list[dict[str, Any]] = Field(default_factory=list)
    prior_outcomes: list[dict[str, Any]] = Field(default_factory=list)


class WorkbenchActionAffordanceList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    program_id: UUID
    entity_key: str
    target: dict[str, Any] = Field(default_factory=dict)
    actions: list[WorkbenchActionAffordance] = Field(default_factory=list)
    rejected: list[WorkbenchActionAffordance] = Field(default_factory=list)
    boundary: dict[str, Any] = Field(default_factory=dict)


class WorkbenchEntityMemory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    program_id: UUID
    entity_key: str
    fragments: list[dict[str, Any]] = Field(default_factory=list)
    tree_nodes: list[dict[str, Any]] = Field(default_factory=list)
    summaries: list[dict[str, Any]] = Field(default_factory=list)
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    boundary: dict[str, Any] = Field(default_factory=dict)


class WorkbenchRetrieveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    program_id: UUID
    selected_entities: list[str] = Field(default_factory=list)
    query: str | None = None
    temporal_scope: dict[str, Any] = Field(default_factory=dict)
    lens: WorkbenchLens = WorkbenchLens.SURFACE


class WorkbenchEvidencePack(BaseModel):
    model_config = ConfigDict(extra="forbid")

    program_id: UUID
    lens: WorkbenchLens
    selected_entities: list[str] = Field(default_factory=list)
    query: str | None = None
    query_terms: list[str] = Field(default_factory=list)
    temporal_scope: dict[str, Any] = Field(default_factory=dict)
    entity_summaries: list[dict[str, Any]] = Field(default_factory=list)
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    fragments: list[dict[str, Any]] = Field(default_factory=list)
    ranked_context: list[dict[str, Any]] = Field(default_factory=list)
    search_projection_refs: list[dict[str, Any]] = Field(default_factory=list)
    graph_context: WorkbenchGraph | None = None
    graph_context_summary: dict[str, Any] = Field(default_factory=dict)
    boundary: dict[str, Any] = Field(default_factory=dict)


class WorkbenchGraphStore(Protocol):
    async def surface_graph(
        self,
        *,
        program_id: UUID,
        seed: str | None = None,
        depth: int = 1,
        limit: int = 250,
    ) -> WorkbenchGraph | None: ...

    async def component_graph(
        self,
        *,
        program_id: UUID,
        seed: str | None = None,
        depth: int = 1,
        limit: int = 250,
    ) -> WorkbenchGraph | None: ...

    async def memory_graph(
        self,
        *,
        program_id: UUID,
        seed: str | None = None,
        depth: int = 1,
        limit: int = 250,
    ) -> WorkbenchGraph | None: ...

    async def action_graph(
        self,
        *,
        program_id: UUID,
        seed: str | None = None,
        depth: int = 1,
        limit: int = 250,
    ) -> WorkbenchGraph | None: ...

    async def hypothesis_graph(
        self,
        *,
        program_id: UUID,
        seed: str | None = None,
        depth: int = 1,
        limit: int = 250,
    ) -> WorkbenchGraph | None: ...

    async def coverage_graph(
        self,
        *,
        program_id: UUID,
        seed: str | None = None,
        depth: int = 1,
        limit: int = 250,
    ) -> WorkbenchGraph | None: ...

    async def neo4j_graph(
        self,
        *,
        program_id: UUID,
        lens: WorkbenchLens,
        seed: str | None = None,
        depth: int = 1,
        limit: int = 250,
    ) -> WorkbenchGraph | None: ...

    async def entity_profile(self, *, program_id: UUID, entity_key: str) -> WorkbenchEntityProfile | None: ...

    async def entity_actions(
        self,
        *,
        program_id: UUID,
        entity_key: str,
        limit: int = 10,
    ) -> WorkbenchActionAffordanceList | None: ...

    async def entity_memory(
        self,
        *,
        program_id: UUID,
        entity_key: str,
        limit: int = 20,
    ) -> WorkbenchEntityMemory | None: ...


class WorkbenchReadService:
    """Assemble workbench read DTOs from typed read models."""

    def __init__(
        self,
        graph_store: WorkbenchGraphStore,
        projection_overview: ProgramProjectionOverviewService,
    ) -> None:
        self._graph_store = graph_store
        self._projection_overview = projection_overview

    async def bootstrap(self, *, program_id: UUID) -> WorkbenchBootstrap:
        overview = await self._overview(program_id)
        return WorkbenchBootstrap(
            program_id=program_id,
            lenses=workbench_lenses(overview),
            projection_freshness=_projection_freshness(overview),
            queue_health=_queue_health(overview),
            counts=_counts(overview),
            default_graph_seed=_default_graph_seed(overview),
            boundary=workbench_read_boundary(surface="bootstrap"),
        )

    async def graph(
        self,
        *,
        program_id: UUID,
        lens: WorkbenchLens = WorkbenchLens.SURFACE,
        seed: str | None = None,
        depth: int = 1,
        limit: int = 250,
    ) -> WorkbenchGraph:
        clamped_depth = max(0, min(depth, 4))
        clamped_limit = max(1, min(limit, 500))
        if lens == WorkbenchLens.SURFACE:
            graph = await self._graph_store.surface_graph(
                program_id=program_id,
                seed=seed,
                depth=clamped_depth,
                limit=clamped_limit,
            )
            if graph is None:
                raise WorkbenchNotFound(f"Workbench surface graph not found for program={program_id}")
            return graph
        if lens == WorkbenchLens.COMPONENTS:
            graph = await self._graph_store.component_graph(
                program_id=program_id,
                seed=seed,
                depth=clamped_depth,
                limit=clamped_limit,
            )
            if graph is None:
                raise WorkbenchNotFound(f"Workbench component graph not found for program={program_id}")
            return graph
        if lens == WorkbenchLens.MEMORY:
            graph = await self._graph_store.memory_graph(
                program_id=program_id,
                seed=seed,
                depth=clamped_depth,
                limit=clamped_limit,
            )
            if graph is None:
                raise WorkbenchNotFound(f"Workbench memory graph not found for program={program_id}")
            return graph
        if lens == WorkbenchLens.ACTION:
            graph = await self._graph_store.action_graph(
                program_id=program_id,
                seed=seed,
                depth=clamped_depth,
                limit=clamped_limit,
            )
            if graph is None:
                raise WorkbenchNotFound(f"Workbench action graph not found for program={program_id}")
            return graph
        if lens == WorkbenchLens.HYPOTHESIS:
            graph = await self._graph_store.hypothesis_graph(
                program_id=program_id,
                seed=seed,
                depth=clamped_depth,
                limit=clamped_limit,
            )
            if graph is None:
                raise WorkbenchNotFound(f"Workbench hypothesis graph not found for program={program_id}")
            return graph
        if lens == WorkbenchLens.COVERAGE:
            graph = await self._graph_store.coverage_graph(
                program_id=program_id,
                seed=seed,
                depth=clamped_depth,
                limit=clamped_limit,
            )
            if graph is None:
                raise WorkbenchNotFound(f"Workbench coverage graph not found for program={program_id}")
            return graph
        if is_neo4j_workbench_lens(lens):
            graph = await self._graph_store.neo4j_graph(
                program_id=program_id,
                lens=lens,
                seed=seed,
                depth=clamped_depth,
                limit=clamped_limit,
            )
            if graph is None:
                raise WorkbenchNotFound(f"Workbench Neo4j graph not found for program={program_id} lens={lens.value}")
            return graph
        return WorkbenchGraph(
            program_id=program_id,
            lens=lens,
            seed=seed,
            depth=depth,
            boundary=workbench_read_boundary(surface=f"{lens.value}_lens_stub"),
        )

    async def entity_profile(self, *, program_id: UUID, entity_key: str) -> WorkbenchEntityProfile:
        profile = await self._graph_store.entity_profile(program_id=program_id, entity_key=entity_key)
        if profile is None:
            raise WorkbenchNotFound(f"Workbench entity not found for program={program_id} entity={entity_key}")
        return profile

    async def entity_actions(self, *, program_id: UUID, entity_key: str) -> WorkbenchActionAffordanceList:
        actions = await self._graph_store.entity_actions(program_id=program_id, entity_key=entity_key)
        if actions is None:
            raise WorkbenchNotFound(f"Workbench entity not found for program={program_id} entity={entity_key}")
        return actions

    async def entity_memory(self, *, program_id: UUID, entity_key: str) -> WorkbenchEntityMemory:
        memory = await self._graph_store.entity_memory(program_id=program_id, entity_key=entity_key)
        if memory is None:
            raise WorkbenchNotFound(f"Workbench entity not found for program={program_id} entity={entity_key}")
        return memory

    async def retrieve(self, request: WorkbenchRetrieveRequest) -> WorkbenchEvidencePack:
        async def load_graph_context(seed: str) -> WorkbenchGraph:
            return await self.graph(
                program_id=request.program_id,
                lens=request.lens,
                seed=seed,
                depth=2,
                limit=200,
            )

        async def load_entity_profile(entity_key: str) -> WorkbenchEntityProfile:
            return await self.entity_profile(program_id=request.program_id, entity_key=entity_key)

        async def load_entity_memory(entity_key: str) -> WorkbenchEntityMemory:
            return await self.entity_memory(program_id=request.program_id, entity_key=entity_key)

        payload = await assemble_evidence_pack_payload(
            program_id=request.program_id,
            lens=request.lens,
            selected_entities=request.selected_entities,
            query=request.query,
            temporal_scope=request.temporal_scope,
            load_graph_context=load_graph_context,
            load_entity_profile=load_entity_profile,
            load_entity_memory=load_entity_memory,
            not_found_exceptions=(WorkbenchNotFound,),
            boundary=workbench_read_boundary(surface="hybrid_retrieval_evidence_pack"),
        )
        return WorkbenchEvidencePack(**payload)

    async def _overview(self, program_id: UUID) -> ProgramProjectionOverview | None:
        try:
            return await self._projection_overview.overview(program_id=program_id)
        except ProgramProjectionOverviewNotFound:
            return None



def is_neo4j_workbench_lens(lens: WorkbenchLens) -> bool:
    return lens in {
        WorkbenchLens.NEO4J_EXPOSURE,
        WorkbenchLens.NEO4J_ENDPOINT,
        WorkbenchLens.NEO4J_EVIDENCE,
        WorkbenchLens.NEO4J_SURFACE_MATH,
        WorkbenchLens.NEO4J_ACTION_OUTCOME,
        WorkbenchLens.NEO4J_JS,
        WorkbenchLens.NEO4J_TECH,
        WorkbenchLens.NEO4J_HYPOTHESIS,
    }


def _neo4j_lens_descriptors() -> list[WorkbenchLensDescriptor]:
    return [
        WorkbenchLensDescriptor(lens=WorkbenchLens.NEO4J_EXPOSURE, label="Neo4j · Exposure", available=True),
        WorkbenchLensDescriptor(lens=WorkbenchLens.NEO4J_ENDPOINT, label="Neo4j · Endpoint", available=True, reason="select_endpoint_seed_for_neighborhood"),
        WorkbenchLensDescriptor(lens=WorkbenchLens.NEO4J_EVIDENCE, label="Neo4j · Evidence", available=True, reason="select_entity_seed_for_evidence_path"),
        WorkbenchLensDescriptor(lens=WorkbenchLens.NEO4J_SURFACE_MATH, label="Neo4j · Surface math", available=True, reason="select_surface_snapshot_seed"),
        WorkbenchLensDescriptor(lens=WorkbenchLens.NEO4J_ACTION_OUTCOME, label="Neo4j · Outcomes", available=True),
        WorkbenchLensDescriptor(lens=WorkbenchLens.NEO4J_JS, label="Neo4j · JS refs", available=True),
        WorkbenchLensDescriptor(lens=WorkbenchLens.NEO4J_TECH, label="Neo4j · Services", available=True),
        WorkbenchLensDescriptor(lens=WorkbenchLens.NEO4J_HYPOTHESIS, label="Neo4j · Hypothesis evidence", available=True),
    ]


def workbench_lenses(overview: ProgramProjectionOverview | None = None) -> list[WorkbenchLensDescriptor]:
    components_available = bool(overview and overview.latest_surface_analysis)
    coverage_available = bool(overview and overview.latest_surface_snapshot)
    return [
        WorkbenchLensDescriptor(lens=WorkbenchLens.SURFACE, label="Surface", available=True, default=True),
        WorkbenchLensDescriptor(
            lens=WorkbenchLens.COMPONENTS,
            label="Components",
            available=components_available,
            reason=None if components_available else "no_materialized_surface_component_analysis",
        ),
        WorkbenchLensDescriptor(lens=WorkbenchLens.MEMORY, label="Memory", available=True),
        WorkbenchLensDescriptor(lens=WorkbenchLens.HYPOTHESIS, label="Hypothesis", available=True),
        WorkbenchLensDescriptor(lens=WorkbenchLens.ACTION, label="Action", available=True),
        WorkbenchLensDescriptor(
            lens=WorkbenchLens.COVERAGE,
            label="Coverage",
            available=coverage_available,
            reason=None if coverage_available else "no_surface_snapshot",
        ),
        *_neo4j_lens_descriptors(),
    ]


def workbench_read_boundary(*, surface: str) -> dict[str, Any]:
    return {
        "surface": surface,
        "postgres_write": "forbidden",
        "neo4j_read": "forbidden",
        "neo4j_write": "forbidden",
        "raw_cypher": "forbidden",
        "gds_execution": "forbidden",
        "graph_rebuild": "forbidden",
        "opensearch_reindex": "forbidden",
        "proposal_creation": "forbidden",
        "action_submission": "forbidden",
        "tool_execution": "forbidden",
        "raw_secret_material": "forbidden",
        "source_of_truth": [
            "surface_snapshots",
            "surface_nodes",
            "surface_edges",
            "surface_deltas",
            "surface_component_analysis_runs",
            "surface_component_analysis_items",
            "projection queues",
            "action_requests",
            "action_request_targets",
            "action_outcomes",
            "runs",
            "raw_artifact references",
            "research_signals",
            "research_hypotheses",
            "research_hypothesis_evidence",
            "research_hypothesis_events",
            "research_hypothesis_score_history",
            "agent_action_proposals",
            "Neo4j graph-projector ontology via allowlisted templates",
        ],
    }


def _projection_freshness(overview: ProgramProjectionOverview | None) -> dict[str, Any]:
    if overview is None:
        return {"available": False, "ui_data_fresh": False}
    return {
        "available": True,
        "surface_analysis_fresh": overview.surface_analysis_fresh,
        "search_index_fresh": overview.search_index_fresh,
        "ui_data_fresh": overview.ui_data_fresh,
        "latest_surface_snapshot": _model_or_none(overview.latest_surface_snapshot),
        "latest_surface_analysis": _model_or_none(overview.latest_surface_analysis),
        "search_index": overview.search_index.model_dump(mode="json"),
    }


def _queue_health(overview: ProgramProjectionOverview | None) -> dict[str, Any]:
    if overview is None:
        return {}
    return {
        "graph_projection_events": overview.graph_projection_events.model_dump(mode="json"),
        "graph_fact_batches": overview.graph_fact_batches.model_dump(mode="json"),
        "surface_analysis_events": overview.surface_analysis_events.model_dump(mode="json"),
        "search_projection_events": overview.search_projection_events.model_dump(mode="json"),
    }


def _counts(overview: ProgramProjectionOverview | None) -> dict[str, int]:
    if overview is None or overview.latest_surface_snapshot is None:
        return {}
    counts = {
        "surface_nodes": overview.latest_surface_snapshot.node_count,
        "surface_edges": overview.latest_surface_snapshot.edge_count,
        "surface_deltas": overview.latest_surface_snapshot.delta_count,
        "experience_proposals_pending": overview.experience_proposals.pending,
    }
    if overview.latest_surface_analysis is not None:
        counts["surface_components"] = overview.latest_surface_analysis.item_count
    return counts


def _default_graph_seed(overview: ProgramProjectionOverview | None) -> str | None:
    # The first surface slice can load the latest graph without a seed. Do not
    # invent a seed token until a backend entity can resolve it.
    return None


def _model_or_none(model: BaseModel | None) -> dict[str, Any] | None:
    return model.model_dump(mode="json") if model is not None else None
