from __future__ import annotations

from datetime import datetime
from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Query

from api.application.agent_activity import AgentActivityService


router = APIRouter(route_class=DishkaRoute)


@router.get(
    "",
    summary="Read agent workroom activity stream",
    description=(
        "Returns incremental visible activity for the campaign workroom: agent "
        "messages, proposals, proposal decisions, and action status updates. "
        "This endpoint is read-only and does not execute agents, GDS, or tools."
    ),
    tags=["Agent Activity"],
)
async def get_agent_activity(
    service: FromDishka[AgentActivityService],
    program_id: UUID,
    campaign_id: UUID | None = None,
    task_id: UUID | None = None,
    after: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    snapshot = await service.get_activity_stream(
        program_id=program_id,
        campaign_id=campaign_id,
        task_id=task_id,
        after=after,
        limit=limit,
    )
    return snapshot.model_dump(mode="json")
