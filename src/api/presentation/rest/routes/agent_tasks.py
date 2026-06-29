from __future__ import annotations

from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException, Query

from api.application.agent_task_detail import AgentTaskDetailService
from api.application.agent_tasks import (
    AgentTaskFollowupRequest,
    AgentTaskPromptRequest,
    AgentTaskService,
    AgentTaskStatus,
)


router = APIRouter(route_class=DishkaRoute)


@router.post(
    "",
    summary="Create agent task from prompt",
    description=(
        "Creates a bounded agent task from a human prompt and enqueues it for "
        "agent processing. The prompt cannot execute tools directly."
    ),
    tags=["Agent Tasks"],
    status_code=202,
)
async def create_agent_task(
    request: AgentTaskPromptRequest,
    service: FromDishka[AgentTaskService],
) -> dict:
    created = await service.create_prompt_task(request)
    return created.model_dump(mode="json")


@router.get(
    "",
    summary="List agent tasks",
    description="Lists user-facing agent tasks for a program or campaign.",
    tags=["Agent Tasks"],
)
async def list_agent_tasks(
    service: FromDishka[AgentTaskService],
    program_id: UUID,
    campaign_id: UUID | None = None,
    status: AgentTaskStatus | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict:
    tasks = await service.list_tasks(
        program_id=program_id,
        campaign_id=campaign_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    return {"items": [task.model_dump(mode="json") for task in tasks]}


@router.get(
    "/{task_id}/detail",
    summary="Read one agent task detail",
    description=(
        "Returns the focused UI read model for one agent task: visible thread, "
        "proposals, decisions, accepted actions, related outcomes, and compact "
        "context. This endpoint does not execute agents, GDS, or tools."
    ),
    tags=["Agent Tasks"],
)
async def get_agent_task_detail(
    task_id: UUID,
    service: FromDishka[AgentTaskDetailService],
    message_limit: int = Query(default=100, ge=1, le=500),
    proposal_limit: int = Query(default=50, ge=1, le=200),
    outcome_limit: int = Query(default=20, ge=1, le=100),
    surface_sample_limit: int = Query(default=8, ge=1, le=50),
) -> dict:
    detail = await service.get_task_detail(
        task_id=task_id,
        message_limit=message_limit,
        proposal_limit=proposal_limit,
        outcome_limit=outcome_limit,
        surface_sample_limit=surface_sample_limit,
    )
    if detail is None:
        raise HTTPException(status_code=404, detail="agent task not found")
    return detail.model_dump(mode="json")


@router.get(
    "/{task_id}/messages",
    summary="List agent task messages",
    description="Lists the visible conversation for one agent task.",
    tags=["Agent Tasks"],
)
async def list_agent_task_messages(
    task_id: UUID,
    service: FromDishka[AgentTaskService],
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict:
    messages = await service.list_task_messages(
        task_id=task_id,
        limit=limit,
        offset=offset,
    )
    return {"items": [message.model_dump(mode="json") for message in messages]}


@router.post(
    "/{task_id}/messages",
    summary="Append human follow-up to agent task",
    description=(
        "Adds a human follow-up prompt to an existing agent task and enqueues "
        "it for bounded agent processing. The message cannot execute tools directly."
    ),
    tags=["Agent Tasks"],
    status_code=202,
)
async def append_agent_task_followup(
    task_id: UUID,
    request: AgentTaskFollowupRequest,
    service: FromDishka[AgentTaskService],
) -> dict:
    message = await service.append_followup_message(
        task_id=task_id,
        request=request,
    )
    return message.model_dump(mode="json")
