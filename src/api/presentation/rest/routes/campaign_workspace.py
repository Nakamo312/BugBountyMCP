from __future__ import annotations

from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Query

from api.application.campaign_workspace import CampaignWorkspaceService


router = APIRouter(route_class=DishkaRoute)


@router.get(
    "",
    summary="Read campaign workroom snapshot",
    description=(
        "Returns the UI read model for the campaign workroom: agent tasks, "
        "visible messages, proposals, decisions, and current action queue. "
        "This endpoint does not execute agents, GDS, or tools."
    ),
    tags=["Campaign Workspace"],
)
async def get_campaign_workspace(
    service: FromDishka[CampaignWorkspaceService],
    program_id: UUID,
    campaign_id: UUID | None = None,
    task_limit: int = Query(default=20, ge=1, le=100),
    message_limit_per_task: int = Query(default=8, ge=1, le=50),
    proposal_limit: int = Query(default=20, ge=1, le=100),
    action_limit: int = Query(default=20, ge=1, le=100),
) -> dict:
    snapshot = await service.get_workspace(
        program_id=program_id,
        campaign_id=campaign_id,
        task_limit=task_limit,
        message_limit_per_task=message_limit_per_task,
        proposal_limit=proposal_limit,
        action_limit=action_limit,
    )
    return snapshot.model_dump(mode="json")
