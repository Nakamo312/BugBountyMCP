"""Async Postgres reader for materialized Surface Component analysis."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import bindparam, desc, nulls_last, select
from sqlalchemy.sql.elements import ColumnElement

from api.application.surface_component_analysis import (
    SurfaceComponentAnalysisItem,
    SurfaceComponentAnalysisReport,
    SurfaceComponentAnalysisStore as SurfaceComponentAnalysisStoreProtocol,
)
from api.infrastructure.adapters.orm import (
    surface_component_analysis_items,
    surface_component_analysis_runs,
)

_RUNS = surface_component_analysis_runs
_ITEMS = surface_component_analysis_items

_RUN_COLUMNS = (
    _RUNS.c.id,
    _RUNS.c.program_id,
    _RUNS.c.snapshot_id,
    _RUNS.c.previous_snapshot_id,
    _RUNS.c.algorithm,
    _RUNS.c.algorithm_version,
    _RUNS.c.report_fingerprint,
    _RUNS.c.settings_json,
    _RUNS.c.stats_json,
    _RUNS.c.created_at,
)

_ITEM_COLUMNS = (
    _ITEMS.c.component_id,
    _ITEMS.c.node_count,
    _ITEMS.c.changed_node_count,
    _ITEMS.c.structural_pressure_score,
    _ITEMS.c.drift_score,
    _ITEMS.c.bridge_pressure_score,
    _ITEMS.c.outlier_score,
    _ITEMS.c.coverage_score,
    _ITEMS.c.exploration_priority_score,
    _ITEMS.c.action_candidate_count,
    _ITEMS.c.metrics_json,
    _ITEMS.c.action_candidates_json,
)


class SurfaceComponentAnalysisStore(SurfaceComponentAnalysisStoreProtocol):
    """Read persisted component analysis without invoking Neo4j/GDS."""

    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

    async def latest(
        self,
        *,
        program_id: UUID,
        snapshot_id: UUID,
        previous_snapshot_id: UUID | None = None,
    ) -> SurfaceComponentAnalysisReport | None:
        predicates = [
            _RUNS.c.program_id == bindparam("program_id"),
            _RUNS.c.snapshot_id == bindparam("snapshot_id"),
            _previous_snapshot_predicate(previous_snapshot_id),
        ]
        return await self._latest_by_predicates(
            predicates=predicates,
            parameters=_latest_parameters(program_id, snapshot_id, previous_snapshot_id),
        )

    async def latest_for_program(
        self,
        *,
        program_id: UUID,
    ) -> SurfaceComponentAnalysisReport | None:
        return await self._latest_by_predicates(
            predicates=[_RUNS.c.program_id == bindparam("program_id")],
            parameters={"program_id": program_id},
        )

    async def _latest_by_predicates(
        self,
        *,
        predicates: list[ColumnElement[bool]],
        parameters: dict[str, object],
    ) -> SurfaceComponentAnalysisReport | None:
        run_statement = (
            select(*_RUN_COLUMNS)
            .where(*predicates)
            .order_by(desc(_RUNS.c.created_at), desc(_RUNS.c.updated_at))
            .limit(1)
        )
        item_statement = (
            select(*_ITEM_COLUMNS)
            .where(_ITEMS.c.analysis_run_id == bindparam("analysis_run_id"))
            .order_by(
                nulls_last(desc(_ITEMS.c.exploration_priority_score)),
                nulls_last(desc(_ITEMS.c.structural_pressure_score)),
                _ITEMS.c.component_id.asc(),
            )
        )
        async with self.session_factory() as session:
            run_result = await session.execute(run_statement, parameters)
            run = run_result.mappings().one_or_none()
            if run is None:
                return None
            item_result = await session.execute(item_statement, {"analysis_run_id": run["id"]})
            items = [_item_from_row(row) for row in item_result.mappings().all()]
        return SurfaceComponentAnalysisReport(
            analysis_run_id=run["id"],
            program_id=run["program_id"],
            snapshot_id=run["snapshot_id"],
            previous_snapshot_id=run["previous_snapshot_id"],
            report_fingerprint=str(run["report_fingerprint"]),
            algorithm=str(run["algorithm"]),
            algorithm_version=str(run["algorithm_version"]),
            stats=dict(run["stats_json"] or {}),
            settings=dict(run["settings_json"] or {}),
            created_at=run["created_at"],
            item_count=len(items),
            items=items,
        )


def _previous_snapshot_predicate(previous_snapshot_id: UUID | None) -> ColumnElement[bool]:
    if previous_snapshot_id is None:
        return _RUNS.c.previous_snapshot_id.is_(None)
    return _RUNS.c.previous_snapshot_id == bindparam("previous_snapshot_id")


def _latest_parameters(program_id: UUID, snapshot_id: UUID, previous_snapshot_id: UUID | None) -> dict[str, object]:
    parameters: dict[str, object] = {"program_id": program_id, "snapshot_id": snapshot_id}
    if previous_snapshot_id is not None:
        parameters["previous_snapshot_id"] = previous_snapshot_id
    return parameters


def _item_from_row(row: Any) -> SurfaceComponentAnalysisItem:
    return SurfaceComponentAnalysisItem(
        component_id=int(row["component_id"]),
        node_count=int(row["node_count"]),
        changed_node_count=int(row["changed_node_count"]),
        structural_pressure_score=_optional_int(row["structural_pressure_score"]),
        drift_score=_optional_int(row["drift_score"]),
        bridge_pressure_score=_optional_int(row["bridge_pressure_score"]),
        outlier_score=_optional_int(row["outlier_score"]),
        coverage_score=_optional_int(row["coverage_score"]),
        exploration_priority_score=_optional_int(row["exploration_priority_score"]),
        action_candidate_count=int(row["action_candidate_count"]),
        metrics=dict(row["metrics_json"] or {}),
        action_candidates=list(row["action_candidates_json"] or []),
    )


def _optional_int(value: Any) -> int | None:
    return int(value) if value is not None else None
