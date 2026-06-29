from __future__ import annotations

from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from api.application.action_catalog import CatalogItemNotFound, CatalogNotReady
from api.application.agent_action_proposals import (
    AgentActionProposalAcceptanceService,
    AgentActionProposalAcceptRequest,
    AgentActionProposalNotActionable,
    AgentActionProposalNotFound,
    AgentActionProposalReviewDecision,
    AgentActionProposalReviewRequest,
    AgentActionProposalReviewService,
    AgentActionProposalStateError,
)
from api.application.execution_limits import ActionInputValidationError


router = APIRouter(route_class=DishkaRoute)


@router.post(
    "/{proposal_id}/accept",
    summary="Accept agent action proposal",
    description=(
        "Accepts a stored agent proposal by submitting a canonical ActionRequest "
        "through ActionService. The proposal itself cannot execute tools directly."
    ),
    tags=["Agent Action Proposals"],
    status_code=202,
)
async def accept_agent_action_proposal(
    proposal_id: UUID,
    request: AgentActionProposalAcceptRequest,
    service: FromDishka[AgentActionProposalAcceptanceService],
) -> JSONResponse:
    try:
        result = await service.accept_as_action(
            proposal_id=proposal_id,
            request=request,
        )
    except AgentActionProposalNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AgentActionProposalNotActionable as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except AgentActionProposalStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ActionInputValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except CatalogNotReady as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except CatalogItemNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return JSONResponse(
        status_code=202,
        content={
            "status": result.action_submission.status.value,
            "message": "Agent proposal accepted through ActionService",
            "results": result.model_dump(mode="json"),
        },
    )


@router.post(
    "/{proposal_id}/reject",
    summary="Reject agent action proposal",
    description=(
        "Rejects a stored agent proposal as explicit human/operator feedback. "
        "The proposal is retained as negative learning signal and no tool execution occurs."
    ),
    tags=["Agent Action Proposals"],
    status_code=200,
)
async def reject_agent_action_proposal(
    proposal_id: UUID,
    request: AgentActionProposalReviewRequest,
    service: FromDishka[AgentActionProposalReviewService],
) -> JSONResponse:
    try:
        result = await service.review(
            proposal_id=proposal_id,
            decision=AgentActionProposalReviewDecision.REJECTED,
            request=request,
        )
    except AgentActionProposalNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AgentActionProposalStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return JSONResponse(
        status_code=200,
        content={
            "status": result.proposal.status.value,
            "message": "Agent proposal rejected as feedback",
            "results": result.model_dump(mode="json"),
        },
    )


@router.post(
    "/{proposal_id}/suppress",
    summary="Suppress agent action proposal",
    description=(
        "Suppresses a stored agent proposal as stronger negative feedback for similar future suggestions. "
        "The proposal is retained as learning signal and no tool execution occurs."
    ),
    tags=["Agent Action Proposals"],
    status_code=200,
)
async def suppress_agent_action_proposal(
    proposal_id: UUID,
    request: AgentActionProposalReviewRequest,
    service: FromDishka[AgentActionProposalReviewService],
) -> JSONResponse:
    try:
        result = await service.review(
            proposal_id=proposal_id,
            decision=AgentActionProposalReviewDecision.SUPPRESSED,
            request=request,
        )
    except AgentActionProposalNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AgentActionProposalStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return JSONResponse(
        status_code=200,
        content={
            "status": result.proposal.status.value,
            "message": "Agent proposal suppressed as feedback",
            "results": result.model_dump(mode="json"),
        },
    )
