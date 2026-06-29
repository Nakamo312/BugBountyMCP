from __future__ import annotations

from typing import Any, Mapping
from uuid import UUID

from .row_codec import adapt_json_parameters_for_cursor, cursor_for
from .surface_component_materialization_builders import (
    SURFACE_COMPONENT_ANALYSIS_ALGORITHM,
    SURFACE_COMPONENT_ANALYSIS_VERSION,
    build_materialization_payload,
    component_items_from_report as _component_items_from_report,
)
from .surface_component_materialization_models import (
    MaterializationConnection,
    MaterializationCursor,
    SurfaceComponentMaterializationResult,
    SurfaceComponentMaterializedItem,
    SurfaceComponentMaterializedReport,
)
from .surface_component_materialization_persistence import replace_analysis_items, upsert_analysis_run
from .surface_component_materialization_statements import (
    MATERIALIZATION_JSON_KEYS,
    SURFACE_COMPONENT_ANALYSIS_ITEMS_FOR_RUN_SQL,
    SURFACE_COMPONENT_ANALYSIS_LATEST_SQL,
    latest_parameters as _latest_parameters,
    materialized_item_from_row as _materialized_item_from_row,
    materialized_report_from_rows,
)
from .surface_component_report import SurfaceComponentReport


class SurfaceComponentAnalysisStore:
    """Persist selected Surface Component report results as a read model.

    This store is deliberately downstream of Neo4j/GDS. It does not calculate
    graph metrics and does not create proposals/actions. It only materializes a
    bounded, versioned snapshot of already-computed component analytics so CLI
    and UI consumers can inspect them without re-running GDS on every read.
    """

    def __init__(self, connection: MaterializationConnection) -> None:
        self._connection = connection

    def materialize(
        self,
        report: SurfaceComponentReport,
        *,
        settings_json: Mapping[str, Any] | None = None,
        algorithm: str = SURFACE_COMPONENT_ANALYSIS_ALGORITHM,
        algorithm_version: str = SURFACE_COMPONENT_ANALYSIS_VERSION,
    ) -> SurfaceComponentMaterializationResult:
        payload = build_materialization_payload(
            report,
            settings_json=settings_json,
            algorithm=algorithm,
            algorithm_version=algorithm_version,
        )
        analysis_run_id = upsert_analysis_run(self._fetchone, payload)
        replace_analysis_items(self._execute, payload, analysis_run_id=analysis_run_id)
        self._connection.commit()
        return payload.result(analysis_run_id)

    def latest(
        self,
        *,
        program_id: UUID | str,
        snapshot_id: UUID | str,
        previous_snapshot_id: UUID | str | None = None,
    ) -> SurfaceComponentMaterializedReport | None:
        run = self._fetchone(
            SURFACE_COMPONENT_ANALYSIS_LATEST_SQL,
            _latest_parameters(program_id, snapshot_id, previous_snapshot_id),
        )
        if run is None:
            return None
        rows = self._fetchall(
            SURFACE_COMPONENT_ANALYSIS_ITEMS_FOR_RUN_SQL,
            {"analysis_run_id": run["id"]},
        )
        return materialized_report_from_rows(run, rows)

    def _execute(self, query: str, parameters: dict[str, object]) -> None:
        cursor = self._cursor()
        parameters = _adapt_json_parameters_for_cursor(cursor, parameters)
        try:
            cursor.execute(query, parameters)
        except Exception:
            self._connection.rollback()
            raise

    def _fetchone(self, query: str, parameters: dict[str, object]) -> Mapping[str, Any] | None:
        cursor = self._cursor()
        parameters = _adapt_json_parameters_for_cursor(cursor, parameters)
        try:
            cursor.execute(query, parameters)
            return cursor.fetchone()
        except Exception:
            self._connection.rollback()
            raise

    def _fetchall(self, query: str, parameters: dict[str, object]) -> list[Mapping[str, Any]]:
        cursor = self._cursor()
        parameters = _adapt_json_parameters_for_cursor(cursor, parameters)
        try:
            cursor.execute(query, parameters)
            return list(cursor.fetchall())
        except Exception:
            self._connection.rollback()
            raise

    def _cursor(self) -> MaterializationCursor:
        return cursor_for(self._connection)


def _adapt_json_parameters_for_cursor(cursor: MaterializationCursor, parameters: dict[str, object]) -> dict[str, object]:
    return adapt_json_parameters_for_cursor(cursor, parameters, json_keys=MATERIALIZATION_JSON_KEYS)
