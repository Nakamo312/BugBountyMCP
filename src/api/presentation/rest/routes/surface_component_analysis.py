from __future__ import annotations

from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException

from api.application.surface_component_analysis import (
    SurfaceComponentAnalysisNotFound,
    SurfaceComponentAnalysisService,
    surface_component_analysis_boundary,
)


router = APIRouter(route_class=DishkaRoute)



@router.get(
    "/latest",
    summary="Read latest materialized Surface Component analysis for a program",
    description=(
        "Returns the newest persisted Surface Component analysis for a program. "
        "This endpoint is read-only and never runs Neo4j/GDS, materialization, "
        "proposal generation, action submission, or tools."
    ),
    tags=["Surface Component Analysis"],
)
async def get_latest_surface_component_analysis(
    service: FromDishka[SurfaceComponentAnalysisService],
    program_id: UUID,
) -> dict:
    try:
        report = await service.latest_for_program(program_id=program_id)
    except SurfaceComponentAnalysisNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "analysis": report.model_dump(mode="json"),
        "boundary": surface_component_analysis_boundary(),
    }


@router.get(
    "",
    summary="Read materialized Surface Component analysis",
    description=(
        "Returns the latest persisted Surface Component analysis for a snapshot. "
        "This endpoint is read-only and never runs Neo4j/GDS, materialization, "
        "proposal generation, action submission, or tools."
    ),
    tags=["Surface Component Analysis"],
)
async def get_surface_component_analysis(
    service: FromDishka[SurfaceComponentAnalysisService],
    program_id: UUID,
    snapshot_id: UUID,
    previous_snapshot_id: UUID | None = None,
) -> dict:
    try:
        report = await service.latest(
            program_id=program_id,
            snapshot_id=snapshot_id,
            previous_snapshot_id=previous_snapshot_id,
        )
    except SurfaceComponentAnalysisNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "analysis": report.model_dump(mode="json"),
        "boundary": surface_component_analysis_boundary(),
    }
