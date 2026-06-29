"""Async PostgreSQL reader for program projection overview."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import bindparam, func, select

from api.application.program_projection_overview import (
    ExperienceProposalStatusSummary,
    LatestSurfaceAnalysisSummary,
    LatestSurfaceSnapshotSummary,
    ProgramProjectionOverview,
    ProgramProjectionOverviewStore as ProgramProjectionOverviewStoreProtocol,
    QueueStatusSummary,
    SearchIndexFreshnessSummary,
    graph_projector_command,
    search_indexer_command,
    program_projection_overview_boundary,
)
from api.infrastructure.adapters.orm import (
    action_experience_proposals,
    graph_fact_batches,
    graph_projection_events,
    search_projection_events,
    surface_component_analysis_events,
    surface_component_analysis_items,
    surface_component_analysis_runs,
    surface_deltas,
    surface_edges,
    surface_nodes,
    surface_snapshots,
)


class ProgramProjectionOverviewStore(ProgramProjectionOverviewStoreProtocol):
    """Read durable pipeline state for one program without side effects."""

    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

    async def overview(self, *, program_id: UUID) -> ProgramProjectionOverview | None:
        async with self.session_factory() as session:
            snapshot = await _one_or_none(session, _latest_surface_snapshot_stmt(), {"program_id": program_id})
            latest_analysis = await _one_or_none(session, _latest_surface_analysis_stmt(), {"program_id": program_id})
            latest_snapshot_analysis = None
            if snapshot is not None:
                latest_snapshot_analysis = await _one_or_none(
                    session,
                    _latest_surface_analysis_stmt(snapshot_id=snapshot["id"]),
                    {"program_id": program_id, "snapshot_id": snapshot["id"]},
                )

            graph_projection_summary = _queue_summary(
                await _all(session, _queue_status_stmt(graph_projection_events), {"program_id": program_id})
            )
            graph_fact_batch_summary = _queue_summary(
                await _all(session, _queue_status_stmt(graph_fact_batches), {"program_id": program_id})
            )
            surface_analysis_summary = _queue_summary(
                await _all(session, _queue_status_stmt(surface_component_analysis_events), {"program_id": program_id})
            )
            search_projection_summary = _queue_summary(
                await _all(session, _queue_status_stmt(search_projection_events), {"program_id": program_id})
            )
            proposals = _proposal_summary(
                await _all(session, _proposal_status_stmt(), {"program_id": program_id})
            )

            search_index = await _search_index_freshness(
                session,
                program_id=program_id,
                analysis=latest_snapshot_analysis,
                snapshot=snapshot,
            )

        if snapshot is None and latest_analysis is None:
            return None

        snapshot_summary = _snapshot_summary(snapshot)
        analysis_summary = _analysis_summary(latest_analysis)
        surface_analysis_fresh = latest_snapshot_analysis is not None
        search_index_fresh = bool(
            surface_analysis_fresh
            and search_index.surface_components_indexed
            and search_index.surface_deltas_indexed
        )
        ui_data_fresh = bool(
            surface_analysis_fresh
            and search_index_fresh
            and _queue_clear(graph_projection_summary)
            and _queue_clear(graph_fact_batch_summary)
            and _queue_clear(surface_analysis_summary)
            and _queue_clear(search_projection_summary)
        )
        suggested_commands = _suggested_commands(
            program_id=program_id,
            snapshot=snapshot_summary,
            analysis=_analysis_summary(latest_snapshot_analysis),
            surface_analysis_fresh=surface_analysis_fresh,
            search_index_fresh=search_index_fresh,
            graph_projection_events=graph_projection_summary,
            graph_fact_batches=graph_fact_batch_summary,
            surface_analysis_events=surface_analysis_summary,
            search_projection_events=search_projection_summary,
        )
        return ProgramProjectionOverview(
            program_id=program_id,
            latest_surface_snapshot=snapshot_summary,
            latest_surface_analysis=analysis_summary,
            surface_analysis_fresh=surface_analysis_fresh,
            search_index_fresh=search_index_fresh,
            ui_data_fresh=ui_data_fresh,
            graph_projection_events=graph_projection_summary,
            graph_fact_batches=graph_fact_batch_summary,
            surface_analysis_events=surface_analysis_summary,
            search_projection_events=search_projection_summary,
            search_index=search_index,
            experience_proposals=proposals,
            suggested_commands=suggested_commands,
            boundary=program_projection_overview_boundary(),
        )


def _latest_surface_snapshot_stmt():
    node_count = (
        select(func.count())
        .select_from(surface_nodes)
        .where(surface_nodes.c.snapshot_id == surface_snapshots.c.id)
        .scalar_subquery()
    )
    edge_count = (
        select(func.count())
        .select_from(surface_edges)
        .where(surface_edges.c.snapshot_id == surface_snapshots.c.id)
        .scalar_subquery()
    )
    delta_count = (
        select(func.count())
        .select_from(surface_deltas)
        .where(surface_deltas.c.to_snapshot_id == surface_snapshots.c.id)
        .scalar_subquery()
    )
    return (
        select(
            surface_snapshots.c.id,
            surface_snapshots.c.snapshot_fingerprint,
            surface_snapshots.c.algorithm,
            surface_snapshots.c.algorithm_version,
            surface_snapshots.c.created_at,
            node_count.label("node_count"),
            edge_count.label("edge_count"),
            delta_count.label("delta_count"),
        )
        .where(surface_snapshots.c.program_id == bindparam("program_id"))
        .order_by(surface_snapshots.c.created_at.desc(), surface_snapshots.c.id.desc())
        .limit(1)
    )


def _latest_surface_analysis_stmt(*, snapshot_id: UUID | None = None):
    statement = (
        select(
            surface_component_analysis_runs.c.id,
            surface_component_analysis_runs.c.snapshot_id,
            surface_component_analysis_runs.c.previous_snapshot_id,
            surface_component_analysis_runs.c.report_fingerprint,
            surface_component_analysis_runs.c.algorithm,
            surface_component_analysis_runs.c.algorithm_version,
            surface_component_analysis_runs.c.created_at,
            func.count(surface_component_analysis_items.c.id).label("item_count"),
        )
        .select_from(
            surface_component_analysis_runs.outerjoin(
                surface_component_analysis_items,
                surface_component_analysis_items.c.analysis_run_id == surface_component_analysis_runs.c.id,
            )
        )
        .where(surface_component_analysis_runs.c.program_id == bindparam("program_id"))
        .group_by(
            surface_component_analysis_runs.c.id,
            surface_component_analysis_runs.c.snapshot_id,
            surface_component_analysis_runs.c.previous_snapshot_id,
            surface_component_analysis_runs.c.report_fingerprint,
            surface_component_analysis_runs.c.algorithm,
            surface_component_analysis_runs.c.algorithm_version,
            surface_component_analysis_runs.c.created_at,
        )
        .order_by(surface_component_analysis_runs.c.created_at.desc(), surface_component_analysis_runs.c.id.desc())
        .limit(1)
    )
    if snapshot_id is not None:
        statement = statement.where(surface_component_analysis_runs.c.snapshot_id == bindparam("snapshot_id"))
    return statement


def _queue_status_stmt(table):
    return (
        select(table.c.status, func.count().label("count"))
        .where(table.c.program_id == bindparam("program_id"))
        .group_by(table.c.status)
    )


def _proposal_status_stmt():
    return (
        select(action_experience_proposals.c.status, func.count().label("count"))
        .where(action_experience_proposals.c.program_id == bindparam("program_id"))
        .group_by(action_experience_proposals.c.status)
    )


def _latest_search_event_stmt():
    return (
        select(
            search_projection_events.c.status,
            search_projection_events.c.processed_at,
            search_projection_events.c.updated_at,
            search_projection_events.c.created_at,
        )
        .where(search_projection_events.c.program_id == bindparam("program_id"))
        .where(search_projection_events.c.target == bindparam("target"))
        .where(search_projection_events.c.source_type == bindparam("source_type"))
        .where(search_projection_events.c.source_id == bindparam("source_id"))
        .order_by(
            func.coalesce(
                search_projection_events.c.processed_at,
                search_projection_events.c.updated_at,
                search_projection_events.c.created_at,
            ).desc(),
            search_projection_events.c.created_at.desc(),
        )
        .limit(1)
    )


async def _one_or_none(session: Any, query: Any, parameters: Mapping[str, object]) -> Mapping[str, Any] | None:
    result = await session.execute(query, dict(parameters))
    return result.mappings().one_or_none()


async def _all(session: Any, query: Any, parameters: Mapping[str, object]) -> list[Mapping[str, Any]]:
    result = await session.execute(query, dict(parameters))
    return list(result.mappings().all())


def _snapshot_summary(row: Mapping[str, Any] | None) -> LatestSurfaceSnapshotSummary | None:
    if row is None:
        return None
    return LatestSurfaceSnapshotSummary(
        snapshot_id=row["id"],
        snapshot_fingerprint=str(row["snapshot_fingerprint"]),
        algorithm=str(row["algorithm"]),
        algorithm_version=str(row["algorithm_version"]),
        node_count=int(row.get("node_count") or 0),
        edge_count=int(row.get("edge_count") or 0),
        delta_count=int(row.get("delta_count") or 0),
        created_at=row["created_at"],
    )


def _analysis_summary(row: Mapping[str, Any] | None) -> LatestSurfaceAnalysisSummary | None:
    if row is None:
        return None
    return LatestSurfaceAnalysisSummary(
        analysis_run_id=row["id"],
        snapshot_id=row["snapshot_id"],
        previous_snapshot_id=row["previous_snapshot_id"],
        report_fingerprint=str(row["report_fingerprint"]),
        algorithm=str(row["algorithm"]),
        algorithm_version=str(row["algorithm_version"]),
        item_count=int(row.get("item_count") or 0),
        created_at=row["created_at"],
    )


def _queue_summary(rows: list[Mapping[str, Any]]) -> QueueStatusSummary:
    counts = {str(row["status"]): int(row["count"]) for row in rows}
    return QueueStatusSummary(
        pending=counts.get("pending", 0),
        locked=counts.get("locked", 0),
        processed=counts.get("processed", 0),
        applied=counts.get("applied", 0),
        failed=counts.get("failed", 0),
        dead=counts.get("dead", 0),
    )


def _queue_clear(summary: QueueStatusSummary) -> bool:
    return summary.unhealthy_count == 0 and summary.backlog_count == 0


def _proposal_summary(rows: list[Mapping[str, Any]]) -> ExperienceProposalStatusSummary:
    counts = {str(row["status"]): int(row["count"]) for row in rows}
    return ExperienceProposalStatusSummary(
        pending=counts.get("pending", 0),
        accepted=counts.get("accepted", 0),
        rejected=counts.get("rejected", 0),
        suppressed=counts.get("suppressed", 0),
    )


async def _search_index_freshness(
    session: Any,
    *,
    program_id: UUID,
    analysis: Mapping[str, Any] | None,
    snapshot: Mapping[str, Any] | None,
) -> SearchIndexFreshnessSummary:
    component_event = None
    if analysis is not None:
        component_event = await _one_or_none(
            session,
            _latest_search_event_stmt(),
            {
                "program_id": program_id,
                "target": "surface-components",
                "source_type": "surface-component-analysis-run",
                "source_id": analysis["id"],
            },
        )
    delta_event = None
    if snapshot is not None:
        delta_event = await _one_or_none(
            session,
            _latest_search_event_stmt(),
            {
                "program_id": program_id,
                "target": "surface-deltas",
                "source_type": "surface-snapshot",
                "source_id": snapshot["id"],
            },
        )
    return SearchIndexFreshnessSummary(
        surface_components_indexed=_is_processed(component_event),
        surface_deltas_indexed=_is_processed(delta_event),
        latest_surface_components_event_status=_status(component_event),
        latest_surface_deltas_event_status=_status(delta_event),
        latest_surface_components_event_at=_event_time(component_event),
        latest_surface_deltas_event_at=_event_time(delta_event),
    )


def _is_processed(row: Mapping[str, Any] | None) -> bool:
    return row is not None and str(row.get("status")) == "processed"


def _status(row: Mapping[str, Any] | None) -> str | None:
    return None if row is None else str(row.get("status"))


def _event_time(row: Mapping[str, Any] | None):
    if row is None:
        return None
    return row.get("processed_at") or row.get("updated_at") or row.get("created_at")


def _suggested_commands(
    *,
    program_id: UUID,
    snapshot: LatestSurfaceSnapshotSummary | None,
    analysis: LatestSurfaceAnalysisSummary | None,
    surface_analysis_fresh: bool,
    search_index_fresh: bool,
    graph_projection_events: QueueStatusSummary,
    graph_fact_batches: QueueStatusSummary,
    surface_analysis_events: QueueStatusSummary,
    search_projection_events: QueueStatusSummary,
) -> list[str]:
    commands: list[str] = []
    if graph_projection_events.failed or graph_projection_events.dead or graph_fact_batches.failed or graph_fact_batches.dead:
        commands.append(graph_projector_command("diagnostics", "--program-id", program_id))
        commands.append(graph_projector_command("retry", "--program-id", program_id))
    if graph_projection_events.backlog_count:
        commands.append(graph_projector_command("process-projection-events", "--program-id", program_id))
    if graph_fact_batches.backlog_count:
        commands.append(graph_projector_command("apply-one"))
    if surface_analysis_events.failed or surface_analysis_events.dead:
        commands.append(graph_projector_command("retry", "--queue", "surface_analysis_events", "--program-id", program_id))
    if surface_analysis_events.backlog_count:
        commands.append(graph_projector_command("process-surface-analysis-events", "--program-id", program_id))
    if snapshot is not None and not surface_analysis_fresh:
        commands.append(graph_projector_command("process-surface-analysis-events", "--program-id", program_id))
        commands.append(graph_projector_command("surface-components-materialize", "--program-id", program_id, "--snapshot-id", snapshot.snapshot_id))
    if search_projection_events.failed or search_projection_events.dead:
        commands.append(search_indexer_command("diagnostics", "--program-id", program_id))
        commands.append(search_indexer_command("retry", "--program-id", program_id))
    if search_projection_events.backlog_count:
        commands.append(search_indexer_command("process-events", "--program-id", program_id))
    if analysis is not None and not search_index_fresh:
        commands.append(search_indexer_command("process-events", "--program-id", program_id))
        commands.append(search_indexer_command("reindex", "--target", "surface-components", "--program-id", program_id, "--analysis-run-id", analysis.analysis_run_id))
        commands.append(search_indexer_command("reindex", "--target", "surface-deltas", "--program-id", program_id, "--snapshot-id", analysis.snapshot_id))
    return _dedupe(commands)


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output
