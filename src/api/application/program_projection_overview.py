"""Read-side overview for projection/materialization/indexing state.

This boundary is intentionally diagnostic. It never runs Neo4j/GDS, retries,
rebuilds, reindexes OpenSearch, creates proposals, submits actions, or executes
any tool. It only reads PostgreSQL durable state so operators can understand why
UI data is fresh, stale, or missing.
"""
from __future__ import annotations

from datetime import datetime
import shlex
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProgramProjectionOverviewNotFound(Exception):
    """Raised when the requested program has no projection state yet."""


def graph_projector_command(*args: object) -> str:
    """Return the canonical local module form for graph-projector ops commands."""

    return _module_command("graph_projector", *args)


def search_indexer_command(*args: object) -> str:
    """Return the canonical local module form for search-indexer ops commands."""

    return _module_command("search_indexer", *args)


def bb_cli_command(*args: object) -> str:
    """Return the canonical local module form for bb CLI commands."""

    return _module_command("bb_cli", *args)


def _module_command(module: str, *args: object) -> str:
    argv = ["python", "-m", module, *(str(arg) for arg in args)]
    return shlex.join(argv)


class QueueStatusSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pending: int = 0
    locked: int = 0
    processed: int = 0
    applied: int = 0
    failed: int = 0
    dead: int = 0

    @property
    def unhealthy_count(self) -> int:
        return self.failed + self.dead

    @property
    def backlog_count(self) -> int:
        return self.pending + self.locked


class LatestSurfaceSnapshotSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot_id: UUID
    snapshot_fingerprint: str
    algorithm: str
    algorithm_version: str
    node_count: int
    edge_count: int
    delta_count: int
    created_at: datetime


class LatestSurfaceAnalysisSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis_run_id: UUID
    snapshot_id: UUID
    previous_snapshot_id: UUID | None = None
    report_fingerprint: str
    algorithm: str
    algorithm_version: str
    item_count: int
    created_at: datetime


class SearchIndexFreshnessSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    surface_components_indexed: bool
    surface_deltas_indexed: bool
    latest_surface_components_event_status: str | None = None
    latest_surface_deltas_event_status: str | None = None
    latest_surface_components_event_at: datetime | None = None
    latest_surface_deltas_event_at: datetime | None = None


class ExperienceProposalStatusSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pending: int = 0
    accepted: int = 0
    rejected: int = 0
    suppressed: int = 0


class ProgramProjectionOverview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    program_id: UUID
    latest_surface_snapshot: LatestSurfaceSnapshotSummary | None = None
    latest_surface_analysis: LatestSurfaceAnalysisSummary | None = None
    surface_analysis_fresh: bool
    search_index_fresh: bool
    ui_data_fresh: bool
    graph_projection_events: QueueStatusSummary
    graph_fact_batches: QueueStatusSummary
    surface_analysis_events: QueueStatusSummary
    search_projection_events: QueueStatusSummary
    search_index: SearchIndexFreshnessSummary
    experience_proposals: ExperienceProposalStatusSummary
    suggested_commands: list[str] = Field(default_factory=list)
    boundary: dict[str, Any] = Field(default_factory=dict)


class ProgramProjectionPlanStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str
    priority: int
    severity: str
    area: str
    title: str
    reason: str
    commands: list[str] = Field(default_factory=list)
    blocks_ui_freshness: bool = False


class ProgramProjectionOperatorPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    program_id: UUID
    ui_data_fresh: bool
    step_count: int
    next_step: ProgramProjectionPlanStep | None = None
    steps: list[ProgramProjectionPlanStep] = Field(default_factory=list)
    boundary: dict[str, Any] = Field(default_factory=dict)


class ProgramProjectionOverviewStore(Protocol):
    async def overview(self, *, program_id: UUID) -> ProgramProjectionOverview | None: ...


class ProgramProjectionOverviewService:
    """Return end-to-end projection state and read-only operator plans."""

    def __init__(self, store: ProgramProjectionOverviewStore) -> None:
        self.store = store

    async def overview(self, *, program_id: UUID) -> ProgramProjectionOverview:
        overview = await self.store.overview(program_id=program_id)
        if overview is None:
            raise ProgramProjectionOverviewNotFound(
                f"Projection overview not found for program={program_id}"
            )
        return overview

    async def operator_plan(self, *, program_id: UUID) -> ProgramProjectionOperatorPlan:
        overview = await self.overview(program_id=program_id)
        steps = build_program_projection_operator_plan(overview)
        return ProgramProjectionOperatorPlan(
            program_id=program_id,
            ui_data_fresh=overview.ui_data_fresh,
            step_count=len(steps),
            next_step=steps[0] if steps else None,
            steps=steps,
            boundary=program_projection_operator_plan_boundary(),
        )


def program_projection_overview_boundary() -> dict[str, Any]:
    return {
        "surface": "read_only_projection_overview",
        "postgres_write": "forbidden",
        "neo4j_read": "forbidden",
        "neo4j_write": "forbidden",
        "gds_execution": "forbidden",
        "graph_rebuild": "forbidden",
        "queue_retry": "forbidden",
        "surface_analysis_materialization": "forbidden",
        "opensearch_reindex": "forbidden",
        "proposal_creation": "forbidden",
        "action_submission": "forbidden",
        "tool_execution": "forbidden",
        "source_of_truth": [
            "surface_snapshots",
            "surface_component_analysis_runs/items",
            "graph_projection_events",
            "graph_fact_batches",
            "surface_component_analysis_events",
            "search_projection_events",
            "action_experience_proposals",
        ],
    }


def program_projection_operator_plan_boundary() -> dict[str, Any]:
    return {
        "surface": "read_only_operator_plan",
        "postgres_write": "forbidden",
        "neo4j_read": "forbidden",
        "neo4j_write": "forbidden",
        "gds_execution": "forbidden",
        "graph_rebuild": "forbidden",
        "queue_retry": "forbidden",
        "surface_analysis_materialization": "forbidden",
        "opensearch_reindex": "forbidden",
        "proposal_creation": "forbidden",
        "action_submission": "forbidden",
        "tool_execution": "forbidden",
        "plan_semantics": "ordered_commands_only_not_execution",
        "source_of_truth": ["ProgramProjectionOverview"],
    }


def build_program_projection_operator_plan(overview: ProgramProjectionOverview) -> list[ProgramProjectionPlanStep]:
    """Convert overview state into an ordered read-only operator plan.

    This is deliberately deterministic and side-effect free. It does not decide
    what to scan or execute; it only orders existing ops commands needed to make
    the materialized UI data fresh.
    """

    steps: list[ProgramProjectionPlanStep] = []

    def add(
        *,
        step_id: str,
        priority: int,
        severity: str,
        area: str,
        title: str,
        reason: str,
        commands: list[str],
        blocks_ui_freshness: bool,
    ) -> None:
        steps.append(
            ProgramProjectionPlanStep(
                step_id=step_id,
                priority=priority,
                severity=severity,
                area=area,
                title=title,
                reason=reason,
                commands=_dedupe_commands(commands),
                blocks_ui_freshness=blocks_ui_freshness,
            )
        )

    if overview.graph_projection_events.unhealthy_count or overview.graph_fact_batches.unhealthy_count:
        add(
            step_id="repair-graph-projection",
            priority=10,
            severity="critical",
            area="graph_projection",
            title="Repair failed graph projection work",
            reason="Graph projection events or graph fact batches contain failed/dead rows.",
            commands=[graph_projector_command("diagnostics", "--program-id", overview.program_id), graph_projector_command("retry", "--program-id", overview.program_id)],
            blocks_ui_freshness=True,
        )

    if overview.graph_projection_events.backlog_count:
        add(
            step_id="process-graph-projection-events",
            priority=20,
            severity="warning",
            area="graph_projection",
            title="Process pending graph projection events",
            reason="Canonical changes have not yet been converted into graph fact batches.",
            commands=[graph_projector_command("process-projection-events", "--program-id", overview.program_id)],
            blocks_ui_freshness=True,
        )

    if overview.graph_fact_batches.backlog_count:
        add(
            step_id="apply-graph-fact-batches",
            priority=30,
            severity="warning",
            area="graph_projection",
            title="Apply pending graph fact batches",
            reason="Graph fact batches are waiting to be applied into the Neo4j projection.",
            commands=[graph_projector_command("apply-one")],
            blocks_ui_freshness=True,
        )

    if overview.surface_analysis_events.unhealthy_count:
        add(
            step_id="repair-surface-analysis-events",
            priority=40,
            severity="critical",
            area="surface_analysis",
            title="Repair failed surface analysis events",
            reason="Surface component analysis materialization events contain failed/dead rows.",
            commands=[
                graph_projector_command("diagnostics", "--program-id", overview.program_id),
                graph_projector_command("retry", "--queue", "surface_analysis_events", "--program-id", overview.program_id),
            ],
            blocks_ui_freshness=True,
        )

    if overview.latest_surface_snapshot is not None and not overview.surface_analysis_fresh:
        add(
            step_id="materialize-surface-analysis",
            priority=50,
            severity="warning",
            area="surface_analysis",
            title="Materialize latest surface component analysis",
            reason="The latest surface snapshot does not have a matching persisted component analysis report.",
            commands=[
                graph_projector_command("process-surface-analysis-events", "--program-id", overview.program_id),
                graph_projector_command("surface-components-materialize", "--program-id", overview.program_id, "--snapshot-id", overview.latest_surface_snapshot.snapshot_id),
            ],
            blocks_ui_freshness=True,
        )

    if overview.search_projection_events.unhealthy_count:
        add(
            step_id="repair-search-projection-events",
            priority=60,
            severity="critical",
            area="search_projection",
            title="Repair failed search projection work",
            reason="OpenSearch projection events contain failed/dead rows.",
            commands=[search_indexer_command("diagnostics", "--program-id", overview.program_id), search_indexer_command("retry", "--program-id", overview.program_id)],
            blocks_ui_freshness=True,
        )

    if overview.search_projection_events.backlog_count:
        add(
            step_id="process-search-projection-events",
            priority=70,
            severity="warning",
            area="search_projection",
            title="Process pending search projection events",
            reason="Incremental OpenSearch projection events are pending or locked.",
            commands=[search_indexer_command("process-events", "--program-id", overview.program_id)],
            blocks_ui_freshness=True,
        )

    if overview.latest_surface_analysis is not None and not overview.search_index_fresh:
        add(
            step_id="refresh-surface-search-index",
            priority=80,
            severity="warning",
            area="search_projection",
            title="Refresh surface component search index",
            reason="Persisted surface component analysis exists, but the related OpenSearch projections are stale or missing.",
            commands=[
                search_indexer_command("process-events", "--program-id", overview.program_id),
                search_indexer_command("reindex", "--target", "surface-components", "--program-id", overview.program_id, "--analysis-run-id", overview.latest_surface_analysis.analysis_run_id),
                search_indexer_command("reindex", "--target", "surface-deltas", "--program-id", overview.program_id, "--snapshot-id", overview.latest_surface_analysis.snapshot_id),
            ],
            blocks_ui_freshness=True,
        )

    if overview.experience_proposals.pending:
        add(
            step_id="review-experience-proposals",
            priority=90,
            severity="info",
            area="operator_review",
            title="Review pending action experience proposals",
            reason="Pending learned proposals need explicit accept/reject/suppress feedback from the operator.",
            commands=[bb_cli_command("--program-id", overview.program_id, "proposal", "list")],
            blocks_ui_freshness=False,
        )

    if not steps and overview.ui_data_fresh:
        add(
            step_id="pipeline-fresh",
            priority=1000,
            severity="info",
            area="status",
            title="Projection pipeline is fresh",
            reason="Surface analysis, search projection, and durable queues are in a fresh state for UI consumption.",
            commands=[bb_cli_command("--program-id", overview.program_id, "projection", "overview")],
            blocks_ui_freshness=False,
        )

    return sorted(steps, key=lambda step: step.priority)


def _dedupe_commands(commands: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for command in commands:
        if command in seen:
            continue
        seen.add(command)
        output.append(command)
    return output
