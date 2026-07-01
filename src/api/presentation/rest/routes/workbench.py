from __future__ import annotations

from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException, Query

from api.application.workbench import (
    WorkbenchLens,
    WorkbenchNotFound,
    WorkbenchReadService,
    WorkbenchRetrieveRequest,
)
from api.application.workbench_projection_control import (
    WorkbenchProjectionControlService,
    WorkbenchProjectionRunRequest,
)

router = APIRouter(route_class=DishkaRoute)


@router.get(
    "/bootstrap",
    summary="Read workbench bootstrap state",
    description=(
        "Returns selected program projection freshness, queue health, lens availability, "
        "and default graph seed. This is a read-only workbench boundary."
    ),
    tags=["Workbench"],
)
async def get_workbench_bootstrap(
    service: FromDishka[WorkbenchReadService],
    program_id: UUID,
) -> dict:
    bootstrap = await service.bootstrap(program_id=program_id)
    return bootstrap.model_dump(mode="json")


@router.get(
    "/graph",
    summary="Read workbench graph",
    description=(
        "Returns a frontend-oriented graph DTO for a workbench lens. Implemented "
        "lenses include surface, components, memory, action, and coverage; future lenses expose stable empty contracts until wired."
    ),
    tags=["Workbench"],
)
async def get_workbench_graph(
    service: FromDishka[WorkbenchReadService],
    program_id: UUID,
    lens: WorkbenchLens = WorkbenchLens.SURFACE,
    seed: str | None = None,
    depth: int = Query(default=1, ge=0, le=4),
    limit: int = Query(default=250, ge=1, le=500),
) -> dict:
    try:
        graph = await service.graph(program_id=program_id, lens=lens, seed=seed, depth=depth, limit=limit)
    except WorkbenchNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return graph.model_dump(mode="json")


@router.get(
    "/entities/{entity_key}",
    summary="Read workbench entity profile",
    description="Returns profile, safe properties, evidence references, and pointers for one workbench entity.",
    tags=["Workbench"],
)
async def get_workbench_entity(
    entity_key: str,
    service: FromDishka[WorkbenchReadService],
    program_id: UUID,
) -> dict:
    try:
        profile = await service.entity_profile(program_id=program_id, entity_key=entity_key)
    except WorkbenchNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return profile.model_dump(mode="json")


@router.get(
    "/entities/{entity_key}/actions",
    summary="Read contextual action affordances",
    description="Returns backend-computed action affordance contract for a selected entity.",
    tags=["Workbench"],
)
async def get_workbench_entity_actions(
    entity_key: str,
    service: FromDishka[WorkbenchReadService],
    program_id: UUID,
) -> dict:
    actions = await service.entity_actions(program_id=program_id, entity_key=entity_key)
    return actions.model_dump(mode="json")


@router.get(
    "/entities/{entity_key}/memory",
    summary="Read entity memory",
    description="Returns memory fragment/tree contract for a selected workbench entity.",
    tags=["Workbench"],
)
async def get_workbench_entity_memory(
    entity_key: str,
    service: FromDishka[WorkbenchReadService],
    program_id: UUID,
) -> dict:
    memory = await service.entity_memory(program_id=program_id, entity_key=entity_key)
    return memory.model_dump(mode="json")


@router.post(
    "/retrieve",
    summary="Read hybrid retrieval evidence pack",
    description="Returns an evidence-pack contract, not a prompt blob or raw database shape.",
    tags=["Workbench"],
)
async def retrieve_workbench_evidence(
    request: WorkbenchRetrieveRequest,
    service: FromDishka[WorkbenchReadService],
) -> dict:
    pack = await service.retrieve(request)
    return pack.model_dump(mode="json")


@router.post(
    "/projections/run",
    summary="Run controlled Workbench projection refresh",
    description=(
        "Runs one of a small set of backend-owned projection refresh operations. "
        "The frontend never sends command text, snapshot IDs are optional, and no actions/tools are submitted."
    ),
    tags=["Workbench"],
)
async def run_workbench_projection_refresh(
    request: WorkbenchProjectionRunRequest,
    service: FromDishka[WorkbenchProjectionControlService],
) -> dict:
    result = await service.run_projection_operation(request)
    return result.model_dump(mode="json")
