"""REST boundary for internal action-experience proposals."""
from __future__ import annotations

from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException

from api.application.action_catalog import CatalogItemNotFound, CatalogNotReady
from api.application.action_experience_proposals import (
    ActionExperienceProposalAcceptRequest,
    ActionExperienceProposalAcceptanceService,
    ActionExperienceProposalNotActionable,
    ActionExperienceProposalNotFound,
    ActionExperienceProposalReviewDecision,
    ActionExperienceProposalReviewRequest,
    ActionExperienceProposalReviewService,
    ActionExperienceProposalStateError,
)
from api.application.execution_limits import ActionInputValidationError

router = APIRouter(route_class=DishkaRoute)


@router.post(
    "/{proposal_id}/accept",
    summary="Accept action-experience proposal",
    description=(
        "Accepts an internal graph/GDS action-experience proposal by submitting "
        "a canonical ActionRequest through ActionService. The proposal never "
        "executes tools directly; policy, scope, approval and budget checks still apply."
    ),
    tags=["Action Experience Proposals"],
    status_code=202,
)
async def accept_action_experience_proposal(
    proposal_id: UUID,
    request: ActionExperienceProposalAcceptRequest,
    service: FromDishka[ActionExperienceProposalAcceptanceService],
) -> dict:
    return await _accept_action_experience_proposal(
        proposal_id=proposal_id,
        request=request,
        service=service,
        retry_failed=False,
    )


@router.post(
    "/{proposal_id}/retry-accept",
    summary="Retry failed action-experience proposal acceptance",
    description=(
        "Retries a proposal left in accept_failed after a transient ActionService "
        "failure. It uses the same deterministic action id as the original accept."
    ),
    tags=["Action Experience Proposals"],
    status_code=202,
)
async def retry_accept_action_experience_proposal(
    proposal_id: UUID,
    request: ActionExperienceProposalAcceptRequest,
    service: FromDishka[ActionExperienceProposalAcceptanceService],
) -> dict:
    return await _accept_action_experience_proposal(
        proposal_id=proposal_id,
        request=request,
        service=service,
        retry_failed=True,
    )


async def _accept_action_experience_proposal(
    *,
    proposal_id: UUID,
    request: ActionExperienceProposalAcceptRequest,
    service: ActionExperienceProposalAcceptanceService,
    retry_failed: bool,
) -> dict:
    try:
        if retry_failed:
            result = await service.retry_accept_failed_as_action(proposal_id=proposal_id, request=request)
        else:
            result = await service.accept_as_action(proposal_id=proposal_id, request=request)
    except ActionExperienceProposalNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ActionExperienceProposalStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ActionExperienceProposalNotActionable as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ActionInputValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except CatalogNotReady as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except CatalogItemNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {
        "proposal": result.proposal.model_dump(mode="json"),
        "action_submission": result.action_submission.model_dump(mode="json"),
        "boundary": {
            "proposal_direct_execution": False,
            "submitted_through_action_service": True,
            "policy_scope_approval_budget_required": True,
        },
    }

async def _review_action_experience_proposal(
    *,
    proposal_id: UUID,
    decision: ActionExperienceProposalReviewDecision,
    request: ActionExperienceProposalReviewRequest,
    service: ActionExperienceProposalReviewService,
) -> dict:
    try:
        result = await service.review(proposal_id=proposal_id, decision=decision, request=request)
    except ActionExperienceProposalNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ActionExperienceProposalStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return {
        "proposal": result.proposal.model_dump(mode="json"),
        "boundary": result.boundary,
    }


@router.post(
    "/{proposal_id}/reject",
    summary="Reject action-experience proposal",
    description=(
        "Rejects an internal graph/GDS action-experience proposal as advisory feedback. "
        "This never submits an action and never rewrites the source ActionOutcome; "
        "the feedback is consumed by proposal review priors."
    ),
    tags=["Action Experience Proposals"],
)
async def reject_action_experience_proposal(
    proposal_id: UUID,
    request: ActionExperienceProposalReviewRequest,
    service: FromDishka[ActionExperienceProposalReviewService],
) -> dict:
    return await _review_action_experience_proposal(
        proposal_id=proposal_id,
        decision=ActionExperienceProposalReviewDecision.REJECTED,
        request=request,
        service=service,
    )


@router.post(
    "/{proposal_id}/suppress",
    summary="Suppress action-experience proposal",
    description=(
        "Suppresses an internal graph/GDS action-experience proposal as stronger advisory feedback. "
        "This never submits an action and never rewrites the source ActionOutcome; "
        "the feedback is consumed by proposal review priors."
    ),
    tags=["Action Experience Proposals"],
)
async def suppress_action_experience_proposal(
    proposal_id: UUID,
    request: ActionExperienceProposalReviewRequest,
    service: FromDishka[ActionExperienceProposalReviewService],
) -> dict:
    return await _review_action_experience_proposal(
        proposal_id=proposal_id,
        decision=ActionExperienceProposalReviewDecision.SUPPRESSED,
        request=request,
        service=service,
    )

