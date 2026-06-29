from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from api.application.action_catalog import CatalogItemNotFound, CatalogNotReady
from api.application.contracts import ActionOutcomeFeedback, ActionRequest, ActionStatus
from api.application.execution_limits import ActionInputValidationError
from api.application.services.action import (
    ActionApprovalStateError,
    ActionNotFoundError,
    ActionOutcomeFeedbackUnavailable,
    ActionOutcomeNotFoundError,
    ActionService,
)
from api.application.services.action_catalog import ActionCatalogService
from api.presentation.schemas import ActionApprovalRequest, ActionRejectionRequest

router = APIRouter(route_class=DishkaRoute)


@router.post(
    "",
    summary="Create action",
    description="Submits a catalog-selected action for policy and execution.",
    tags=["Actions"],
    status_code=202,
)
async def create_action(
    request: ActionRequest,
    action_service: FromDishka[ActionService],
) -> JSONResponse:
    try:
        submission = await action_service.request_action(request)
    except ActionInputValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except CatalogNotReady as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except CatalogItemNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return _action_response(submission, status_code=202)


@router.get(
    "/catalog",
    summary="List action catalog",
    description="Lists active action catalog entries.",
    tags=["Actions"],
)
async def list_action_catalog(
    catalog_service: FromDishka[ActionCatalogService],
) -> dict:
    try:
        items = await catalog_service.list_items()
    except CatalogNotReady as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"items": [item.model_dump(mode="json") for item in items]}


@router.get(
    "/catalog/{item_id}",
    summary="Get action catalog item",
    description="Returns detail for one active action catalog entry.",
    tags=["Actions"],
)
async def get_action_catalog_item(
    item_id: UUID,
    catalog_service: FromDishka[ActionCatalogService],
) -> dict:
    try:
        item = await catalog_service.get_detail(item_id)
    except CatalogNotReady as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except CatalogItemNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return item.model_dump(mode="json")


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


@router.get(
    "/{action_id}",
    summary="Get action",
    description="Returns one stored control-plane action.",
    tags=["Actions"],
)
async def get_action(
    action_id: UUID,
    action_service: FromDishka[ActionService],
) -> dict:
    try:
        action = await action_service.get_action(action_id)
    except ActionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return action.model_dump(mode="json")


@router.get(
    "/{action_id}/events",
    summary="List action events",
    description="Lists stored control-plane events for one action.",
    tags=["Actions"],
)
async def list_action_events(
    action_id: UUID,
    action_service: FromDishka[ActionService],
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict:
    try:
        events = await action_service.list_action_events(
            action_id,
            limit=limit,
            offset=offset,
        )
    except ActionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"items": [event.model_dump(mode="json") for event in events]}


@router.get(
    "/{action_id}/result",
    summary="Get action result",
    description="Returns run summaries and artifact references for one action.",
    tags=["Actions"],
)
async def get_action_result(
    action_id: UUID,
    action_service: FromDishka[ActionService],
) -> dict:
    try:
        result = await action_service.get_action_result(action_id)
    except ActionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return result.model_dump(mode="json")


@router.post(
    "/{action_id}/outcome-feedback",
    summary="Record action outcome feedback",
    description="Stores human or workflow feedback on a completed action outcome.",
    tags=["Actions"],
    status_code=200,
)
async def record_action_outcome_feedback(
    action_id: UUID,
    request: ActionOutcomeFeedback,
    action_service: FromDishka[ActionService],
) -> dict:
    try:
        feedback = await action_service.record_outcome_feedback(
            action_id=action_id,
            feedback=request,
        )
    except ActionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ActionOutcomeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ActionOutcomeFeedbackUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return feedback.model_dump(mode="json")


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

    return _action_response(submission, status_code=202)


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

    return _action_response(submission, status_code=200)


def _action_response(submission, *, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "status": submission.status.value,
            "message": submission.message,
            "results": submission.model_dump(mode="json"),
        },
    )
