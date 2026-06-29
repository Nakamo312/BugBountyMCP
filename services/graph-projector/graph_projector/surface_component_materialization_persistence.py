from __future__ import annotations

from collections.abc import Callable
from typing import Any, Mapping
from uuid import UUID, uuid4

from .surface_component_materialization_models import SurfaceComponentMaterializationPayload
from .surface_component_materialization_statements import (
    SURFACE_COMPONENT_ANALYSIS_ITEM_INSERT_SQL,
    SURFACE_COMPONENT_ANALYSIS_ITEMS_DELETE_SQL,
    SURFACE_COMPONENT_ANALYSIS_RUN_UPSERT_SQL,
    analysis_item_values,
    analysis_items_delete_values,
    analysis_run_values,
)

FetchOne = Callable[[str, dict[str, object]], Mapping[str, Any] | None]
Execute = Callable[[str, dict[str, object]], None]


def upsert_analysis_run(fetchone: FetchOne, payload: SurfaceComponentMaterializationPayload) -> UUID:
    row = fetchone(SURFACE_COMPONENT_ANALYSIS_RUN_UPSERT_SQL, analysis_run_values(payload))
    if row is None:
        raise RuntimeError("surface_component_analysis_runs insert did not return an id")
    return UUID(str(row["id"]))


def replace_analysis_items(execute: Execute, payload: SurfaceComponentMaterializationPayload, *, analysis_run_id: UUID) -> None:
    execute(SURFACE_COMPONENT_ANALYSIS_ITEMS_DELETE_SQL, analysis_items_delete_values(analysis_run_id))
    for item in payload.items:
        execute(
            SURFACE_COMPONENT_ANALYSIS_ITEM_INSERT_SQL,
            analysis_item_values(
                item,
                analysis_run_id=analysis_run_id,
                program_id=payload.program_id,
                snapshot_id=payload.snapshot_id,
                item_id=uuid4(),
            ),
        )
