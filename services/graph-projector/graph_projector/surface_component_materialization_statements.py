from __future__ import annotations

from typing import Any, Mapping
from uuid import UUID

from .row_codec import optional_int as _optional_int
from .surface_component_materialization_models import (
    SurfaceComponentMaterializationPayload,
    SurfaceComponentMaterializedItem,
    SurfaceComponentMaterializedReport,
)

SURFACE_COMPONENT_ANALYSIS_LATEST_SQL = """
SELECT id,
       program_id,
       snapshot_id,
       previous_snapshot_id,
       algorithm,
       algorithm_version,
       report_fingerprint,
       settings_json,
       stats_json,
       created_at
FROM surface_component_analysis_runs
WHERE program_id = %(program_id)s
  AND snapshot_id = %(snapshot_id)s
  AND (
      (%(previous_snapshot_id)s IS NULL AND previous_snapshot_id IS NULL)
      OR previous_snapshot_id = %(previous_snapshot_id)s
  )
ORDER BY created_at DESC, updated_at DESC
LIMIT 1;
""".strip()

SURFACE_COMPONENT_ANALYSIS_RUN_UPSERT_SQL = """
INSERT INTO surface_component_analysis_runs (
    id,
    program_id,
    snapshot_id,
    previous_snapshot_id,
    algorithm,
    algorithm_version,
    report_fingerprint,
    settings_json,
    stats_json
)
VALUES (
    %(id)s,
    %(program_id)s,
    %(snapshot_id)s,
    %(previous_snapshot_id)s,
    %(algorithm)s,
    %(algorithm_version)s,
    %(report_fingerprint)s,
    %(settings_json)s,
    %(stats_json)s
)
ON CONFLICT (program_id, report_fingerprint) DO UPDATE
SET snapshot_id = EXCLUDED.snapshot_id,
    previous_snapshot_id = EXCLUDED.previous_snapshot_id,
    settings_json = EXCLUDED.settings_json,
    stats_json = EXCLUDED.stats_json,
    updated_at = now()
RETURNING id;
""".strip()

SURFACE_COMPONENT_ANALYSIS_ITEMS_DELETE_SQL = """
DELETE FROM surface_component_analysis_items WHERE analysis_run_id = %(analysis_run_id)s;
""".strip()

SURFACE_COMPONENT_ANALYSIS_ITEM_INSERT_SQL = """
INSERT INTO surface_component_analysis_items (
    id,
    analysis_run_id,
    program_id,
    snapshot_id,
    component_id,
    node_count,
    changed_node_count,
    structural_pressure_score,
    drift_score,
    bridge_pressure_score,
    outlier_score,
    coverage_score,
    exploration_priority_score,
    action_candidate_count,
    metrics_json,
    action_candidates_json
)
VALUES (
    %(id)s,
    %(analysis_run_id)s,
    %(program_id)s,
    %(snapshot_id)s,
    %(component_id)s,
    %(node_count)s,
    %(changed_node_count)s,
    %(structural_pressure_score)s,
    %(drift_score)s,
    %(bridge_pressure_score)s,
    %(outlier_score)s,
    %(coverage_score)s,
    %(exploration_priority_score)s,
    %(action_candidate_count)s,
    %(metrics_json)s,
    %(action_candidates_json)s
);
""".strip()

SURFACE_COMPONENT_ANALYSIS_ITEMS_FOR_RUN_SQL = """
SELECT component_id,
       node_count,
       changed_node_count,
       structural_pressure_score,
       drift_score,
       bridge_pressure_score,
       outlier_score,
       coverage_score,
       exploration_priority_score,
       action_candidate_count,
       metrics_json,
       action_candidates_json
FROM surface_component_analysis_items
WHERE analysis_run_id = %(analysis_run_id)s
ORDER BY exploration_priority_score DESC NULLS LAST,
         structural_pressure_score DESC NULLS LAST,
         component_id ASC;
""".strip()

MATERIALIZATION_JSON_KEYS = frozenset({"settings_json", "stats_json", "metrics_json", "action_candidates_json"})


def analysis_run_values(payload: SurfaceComponentMaterializationPayload) -> dict[str, object]:
    return {
        "id": str(payload.run_id),
        "program_id": payload.program_id,
        "snapshot_id": payload.snapshot_id,
        "previous_snapshot_id": payload.previous_snapshot_id,
        "algorithm": payload.algorithm,
        "algorithm_version": payload.algorithm_version,
        "report_fingerprint": payload.report_fingerprint,
        "settings_json": payload.settings_json,
        "stats_json": payload.stats_json,
    }


def analysis_items_delete_values(analysis_run_id: UUID) -> dict[str, object]:
    return {"analysis_run_id": analysis_run_id}


def analysis_item_values(
    item: SurfaceComponentMaterializedItem,
    *,
    analysis_run_id: UUID,
    program_id: str,
    snapshot_id: str,
    item_id: UUID,
) -> dict[str, object]:
    return {
        "id": str(item_id),
        "analysis_run_id": analysis_run_id,
        "program_id": program_id,
        "snapshot_id": snapshot_id,
        **item.to_dict(),
    }


def latest_parameters(program_id: UUID | str, snapshot_id: UUID | str, previous_snapshot_id: UUID | str | None) -> dict[str, object]:
    return {
        "program_id": program_id,
        "snapshot_id": snapshot_id,
        "previous_snapshot_id": previous_snapshot_id,
    }


def materialized_item_from_row(row: Mapping[str, Any]) -> SurfaceComponentMaterializedItem:
    return SurfaceComponentMaterializedItem(
        component_id=int(row["component_id"]),
        node_count=int(row["node_count"]),
        changed_node_count=int(row["changed_node_count"]),
        structural_pressure_score=_optional_int(row.get("structural_pressure_score")),
        drift_score=_optional_int(row.get("drift_score")),
        bridge_pressure_score=_optional_int(row.get("bridge_pressure_score")),
        outlier_score=_optional_int(row.get("outlier_score")),
        coverage_score=_optional_int(row.get("coverage_score")),
        exploration_priority_score=_optional_int(row.get("exploration_priority_score")),
        action_candidate_count=int(row["action_candidate_count"]),
        metrics_json=dict(row.get("metrics_json") or {}),
        action_candidates_json=list(row.get("action_candidates_json") or []),
    )


def materialized_report_from_rows(run: Mapping[str, Any], rows: list[Mapping[str, Any]]) -> SurfaceComponentMaterializedReport:
    return SurfaceComponentMaterializedReport(
        analysis_run_id=UUID(str(run["id"])),
        program_id=str(run["program_id"]),
        snapshot_id=str(run["snapshot_id"]),
        previous_snapshot_id=str(run["previous_snapshot_id"]) if run["previous_snapshot_id"] is not None else None,
        report_fingerprint=str(run["report_fingerprint"]),
        algorithm=str(run["algorithm"]),
        algorithm_version=str(run["algorithm_version"]),
        stats_json=dict(run["stats_json"] or {}),
        settings_json=dict(run["settings_json"] or {}),
        created_at=run["created_at"],
        items=tuple(materialized_item_from_row(row) for row in rows),
    )
