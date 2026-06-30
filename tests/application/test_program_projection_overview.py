from __future__ import annotations

import ast
from datetime import datetime, timezone
import inspect
from uuid import uuid4

import pytest

from api.application import program_projection_overview
from api.application.program_projection_overview import (
    bb_cli_command,
    graph_projector_command,
    search_indexer_command,
    LatestSurfaceAnalysisSummary,
    LatestSurfaceSnapshotSummary,
    ProgramProjectionOverview,
    ProgramProjectionOverviewNotFound,
    ProgramProjectionOverviewService,
    QueueStatusSummary,
    build_program_projection_operator_plan,
    SearchIndexFreshnessSummary,
    ExperienceProposalStatusSummary,
)


class _Store:
    def __init__(self, overview):
        self.overview_value = overview
        self.program_id = None

    async def overview(self, *, program_id):
        self.program_id = program_id
        return self.overview_value


def _overview(program_id):
    snapshot_id = uuid4()
    return ProgramProjectionOverview(
        program_id=program_id,
        latest_surface_snapshot=LatestSurfaceSnapshotSummary(
            snapshot_id=snapshot_id,
            snapshot_fingerprint="f" * 64,
            algorithm="surface-map",
            algorithm_version="v1",
            node_count=3,
            edge_count=2,
            delta_count=1,
            created_at=datetime(2026, 6, 27, tzinfo=timezone.utc),
        ),
        surface_analysis_fresh=False,
        search_index_fresh=False,
        ui_data_fresh=False,
        graph_projection_events=QueueStatusSummary(pending=1),
        graph_fact_batches=QueueStatusSummary(),
        surface_analysis_events=QueueStatusSummary(),
        search_projection_events=QueueStatusSummary(),
        search_index=SearchIndexFreshnessSummary(surface_components_indexed=False, surface_deltas_indexed=False),
        experience_proposals=ExperienceProposalStatusSummary(pending=2),
        suggested_commands=["python -m graph_projector process-projection-events --program-id x"],
        boundary={"gds_execution": "forbidden"},
    )


def test_operator_command_helpers_build_shell_safe_module_commands() -> None:
    program_id = uuid4()

    graph_command = graph_projector_command("retry", "--queue", "surface_analysis_events", "--program-id", program_id)
    search_command = search_indexer_command("reindex", "--target", "surface-components", "--analysis-run-id", "run id")
    bb_command = bb_cli_command("--program-id", program_id, "proposal", "list")

    assert graph_command == f"python -m graph_projector retry --queue surface_analysis_events --program-id {program_id}"
    assert search_command == "python -m search_indexer reindex --target surface-components --analysis-run-id 'run id'"
    assert bb_command == f"python -m bb_cli --program-id {program_id} proposal list"


def test_operator_plan_commands_are_built_from_argv_parts() -> None:
    program_id = uuid4()
    snapshot_id = uuid4()
    analysis_run_id = uuid4()
    overview = _overview(program_id).model_copy(
        update={
            "latest_surface_snapshot": _overview(program_id).latest_surface_snapshot.model_copy(update={"snapshot_id": snapshot_id}),
            "latest_surface_analysis": LatestSurfaceAnalysisSummary(
                analysis_run_id=analysis_run_id,
                snapshot_id=snapshot_id,
                previous_snapshot_id=None,
                report_fingerprint="a" * 64,
                algorithm="surface-gds",
                algorithm_version="v1",
                item_count=1,
                created_at=datetime(2026, 6, 27, tzinfo=timezone.utc),
            ),
            "surface_analysis_fresh": False,
            "search_index_fresh": False,
            "graph_projection_events": QueueStatusSummary(),
            "surface_analysis_events": QueueStatusSummary(dead=1),
            "search_projection_events": QueueStatusSummary(dead=1),
            "experience_proposals": ExperienceProposalStatusSummary(),
        }
    )

    commands = [command for step in build_program_projection_operator_plan(overview) for command in step.commands]

    assert all("{program_arg}" not in command for command in commands)
    assert graph_projector_command("surface-components-materialize", "--program-id", program_id, "--snapshot-id", snapshot_id) in commands
    assert search_indexer_command("reindex", "--target", "surface-components", "--program-id", program_id, "--analysis-run-id", analysis_run_id) in commands


def test_operator_plan_builder_is_a_rules_evaluator() -> None:
    source = inspect.getsource(program_projection_overview.build_program_projection_operator_plan)
    tree = ast.parse(source)

    assert len([node for node in ast.walk(tree) if isinstance(node, ast.If)]) <= 1


@pytest.mark.asyncio
async def test_program_projection_overview_service_returns_store_value() -> None:
    program_id = uuid4()
    store = _Store(_overview(program_id))
    service = ProgramProjectionOverviewService(store)

    result = await service.overview(program_id=program_id)

    assert result.program_id == program_id
    assert result.latest_surface_snapshot is not None
    assert result.latest_surface_snapshot.node_count == 3
    assert result.graph_projection_events.pending == 1
    assert result.experience_proposals.pending == 2
    assert result.boundary["gds_execution"] == "forbidden"
    assert store.program_id == program_id


@pytest.mark.asyncio
async def test_program_projection_overview_service_raises_when_missing() -> None:
    service = ProgramProjectionOverviewService(_Store(None))

    with pytest.raises(ProgramProjectionOverviewNotFound):
        await service.overview(program_id=uuid4())


@pytest.mark.asyncio
async def test_program_projection_overview_service_returns_operator_plan() -> None:
    program_id = uuid4()
    overview = _overview(program_id)
    service = ProgramProjectionOverviewService(_Store(overview))

    plan = await service.operator_plan(program_id=program_id)

    assert plan.program_id == program_id
    assert plan.ui_data_fresh is False
    assert plan.step_count >= 1
    assert plan.next_step is not None
    assert plan.boundary["gds_execution"] == "forbidden"


def test_program_projection_operator_plan_orders_blocking_steps() -> None:
    program_id = uuid4()
    overview = _overview(program_id).model_copy(
        update={
            "graph_projection_events": QueueStatusSummary(failed=1),
            "graph_fact_batches": QueueStatusSummary(pending=1),
            "surface_analysis_events": QueueStatusSummary(dead=1),
            "search_projection_events": QueueStatusSummary(pending=2),
            "experience_proposals": ExperienceProposalStatusSummary(pending=3),
        }
    )

    steps = build_program_projection_operator_plan(overview)

    assert [step.priority for step in steps] == sorted(step.priority for step in steps)
    assert steps[0].step_id == "repair-graph-projection"
    assert any(step.step_id == "apply-graph-fact-batches" for step in steps)
    assert any(step.step_id == "review-experience-proposals" for step in steps)
    assert any("python -m graph_projector retry" in command for command in steps[0].commands)


def test_program_projection_operator_plan_treats_locked_rows_as_backlog() -> None:
    program_id = uuid4()
    overview = _overview(program_id).model_copy(
        update={
            "surface_analysis_fresh": True,
            "search_index_fresh": True,
            "graph_projection_events": QueueStatusSummary(locked=1),
            "graph_fact_batches": QueueStatusSummary(locked=1),
            "search_projection_events": QueueStatusSummary(locked=1),
            "experience_proposals": ExperienceProposalStatusSummary(),
        }
    )

    steps = build_program_projection_operator_plan(overview)

    assert any(step.step_id == "process-graph-projection-events" for step in steps)
    assert any(step.step_id == "apply-graph-fact-batches" for step in steps)
    assert any(step.step_id == "process-search-projection-events" for step in steps)
