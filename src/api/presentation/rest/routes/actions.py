from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from api.application.contracts import ActionStatus
from api.application.services.action import (
    ActionApprovalStateError,
    ActionNotFoundError,
    ActionService,
)
from api.presentation.schemas import ActionApprovalRequest, ActionRejectionRequest

router = APIRouter(route_class=DishkaRoute)


@router.get(
    "",
    summary="List actions",
    description="Lists stored control-plane actions, optionally filtered by status or program.",
    tags=["Actions"],
)
async def list_actions(
    action_service: FromDishka[ActionService],
    status: ActionStatus | None = None,
    program_id: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict:
    actions = await action_service.list_actions(
        status=status,
        program_id=program_id,
        limit=limit,
        offset=offset,
    )
    return {"items": [action.model_dump(mode="json") for action in actions]}


@router.get(
    "/pending-approval",
    summary="List actions awaiting approval",
    description="Lists actions currently held in requires_approval state.",
    tags=["Actions"],
)
async def list_pending_approval_actions(
    action_service: FromDishka[ActionService],
    program_id: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict:
    actions = await action_service.list_actions(
        status=ActionStatus.REQUIRES_APPROVAL,
        program_id=program_id,
        limit=limit,
        offset=offset,
    )
    return {"items": [action.model_dump(mode="json") for action in actions]}


@router.post(
    "/{action_id}/approve",
    summary="Approve held action",
    description="Approves an action in requires_approval state and queues it for execution.",
    tags=["Actions"],
    status_code=202,
)
async def approve_action(
    action_id: UUID,
    request: ActionApprovalRequest,
    action_service: FromDishka[ActionService],
) -> JSONResponse:
    try:
        submission = await action_service.approve_action(
            action_id=action_id,
            approved_by=request.approved_by,
            reason=request.reason,
        )
    except ActionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ActionApprovalStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return JSONResponse(
        status_code=202,
        content={
            "status": submission.status.value,
            "message": submission.message,
            "results": submission.model_dump(mode="json"),
        },
    )


@router.post(
    "/{action_id}/reject",
    summary="Reject held action",
    description="Rejects an action in requires_approval state without queueing work.",
    tags=["Actions"],
    status_code=200,
)
async def reject_action(
    action_id: UUID,
    request: ActionRejectionRequest,
    action_service: FromDishka[ActionService],
) -> JSONResponse:
    try:
        submission = await action_service.reject_action(
            action_id=action_id,
            rejected_by=request.rejected_by,
            reason=request.reason,
        )
    except ActionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ActionApprovalStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return JSONResponse(
        status_code=200,
        content={
            "status": submission.status.value,
            "message": submission.message,
            "results": submission.model_dump(mode="json"),
        },
    )
