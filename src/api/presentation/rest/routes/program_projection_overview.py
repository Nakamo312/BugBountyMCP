from __future__ import annotations

from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException

from api.application.program_projection_overview import (
    ProgramProjectionOverviewNotFound,
    ProgramProjectionOverviewService,
)


router = APIRouter(route_class=DishkaRoute)


@router.get(
    "",
    summary="Read program projection overview",
    description=(
        "Returns a read-only end-to-end projection overview for one program. "
        "It reads PostgreSQL durable state only and never runs Neo4j/GDS, "
        "rebuild, retry, materialization, OpenSearch reindex, proposal creation, "
        "action submission, or tools."
    ),
    tags=["Program Projection Overview"],
)
async def get_program_projection_overview(
    service: FromDishka[ProgramProjectionOverviewService],
    program_id: UUID,
) -> dict:
    try:
        overview = await service.overview(program_id=program_id)
    except ProgramProjectionOverviewNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return overview.model_dump(mode="json")


@router.get(
    "/plan",
    summary="Read program projection operator plan",
    description=(
        "Returns an ordered read-only operator plan derived from the program "
        "projection overview. It never executes suggested commands or mutates "
        "projection, materialization, search, proposals, actions, or tools."
    ),
    tags=["Program Projection Overview"],
)
async def get_program_projection_operator_plan(
    service: FromDishka[ProgramProjectionOverviewService],
    program_id: UUID,
) -> dict:
    try:
        plan = await service.operator_plan(program_id=program_id)
    except ProgramProjectionOverviewNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return plan.model_dump(mode="json")
