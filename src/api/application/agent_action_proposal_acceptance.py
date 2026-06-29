"""Accept stored agent action proposals through ActionService."""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID, uuid4

from api.application.agent_tasks import AgentTaskAgentReplyRequest, AgentTaskMessageKind
from api.application.contracts import ActionKind, ActionRequest, ActionSubmission
from api.application.research.sanitizer import sanitize_json

from .agent_action_proposal_models import (
    AGENT_ACTION_PROPOSAL_ACCEPT_SCHEMA_VERSION,
    AGENT_ACTION_PROPOSAL_THREAD_EVENT_SCHEMA_VERSION,
    AgentActionProposalAcceptRequest,
    AgentActionProposalAcceptResult,
    AgentActionProposalNotActionable,
    AgentActionProposalNotFound,
    AgentActionProposalRecord,
    AgentActionProposalStateError,
    AgentActionProposalStatus,
)
from .agent_action_proposal_payloads import (
    options_from_accept_request,
    proposal_record_ref,
    targets_from_accept_request,
)
from .agent_action_proposal_ports import (
    ActionCatalogResolver,
    ActionRequestSubmitter,
    AgentActionProposalStore,
    AgentTaskThreadWriter,
)

logger = logging.getLogger(__name__)


class AgentActionProposalAcceptanceService:
    """Accept stored agent proposals by submitting canonical ActionRequests."""

    def __init__(
        self,
        *,
        store: AgentActionProposalStore,
        action_service: ActionRequestSubmitter,
        catalog_service: ActionCatalogResolver,
        task_thread: AgentTaskThreadWriter | None = None,
    ) -> None:
        self.store = store
        self.action_service = action_service
        self.catalog_service = catalog_service
        self.task_thread = task_thread

    async def accept_as_action(
        self,
        *,
        proposal_id: UUID,
        request: AgentActionProposalAcceptRequest,
    ) -> AgentActionProposalAcceptResult:
        proposal = await self._load_pending_proposal(proposal_id)
        capability_id, profile_id = self._resolve_capability_profile(proposal, request)
        targets = targets_from_accept_request(request, proposal)
        if not targets:
            raise AgentActionProposalNotActionable("proposal needs explicit targets before it can become an action")
        options = options_from_accept_request(request, proposal)
        detail = await self.catalog_service.find_detail(capability=capability_id, profile=profile_id)
        action = self._action_request(
            proposal=proposal,
            request=request,
            catalog_id=detail.id,
            targets=targets,
            options=options,
        )
        submission = await self.action_service.request_action(action, confidence=request.confidence)
        accepted = await self._mark_accepted(proposal=proposal, submission=submission, request=request)
        await self._append_accept_thread_event(proposal=accepted, action_submission=submission, request=request)
        return AgentActionProposalAcceptResult(proposal=accepted, action_submission=submission)

    async def _load_pending_proposal(self, proposal_id: UUID) -> AgentActionProposalRecord:
        proposal = await self.store.get_proposal(proposal_id)
        if proposal is None:
            raise AgentActionProposalNotFound(f"Agent action proposal not found: {proposal_id}")
        if proposal.status is not AgentActionProposalStatus.PENDING:
            raise AgentActionProposalStateError(
                f"Agent action proposal {proposal_id} is not pending: {proposal.status.value}"
            )
        return proposal

    def _resolve_capability_profile(
        self,
        proposal: AgentActionProposalRecord,
        request: AgentActionProposalAcceptRequest,
    ) -> tuple[str, str]:
        capability_id = request.capability_id or proposal.capability_id
        profile_id = request.profile_id or proposal.profile_id
        if not capability_id or not profile_id:
            raise AgentActionProposalNotActionable(
                "proposal needs an explicit capability_id and profile_id before it can become an action"
            )
        return capability_id, profile_id

    def _action_request(
        self,
        *,
        proposal: AgentActionProposalRecord,
        request: AgentActionProposalAcceptRequest,
        catalog_id: UUID,
        targets: list[str],
        options: dict[str, Any],
    ) -> ActionRequest:
        return ActionRequest(
            kind=ActionKind.SCAN,
            program_id=proposal.program_id,
            catalog_id=catalog_id,
            targets=targets,
            options=options,
            budget=request.budget,
            requested_by=request.accepted_by,
            campaign_id=proposal.campaign_id or uuid4(),
            metadata=_action_metadata(proposal=proposal, request=request),
        )

    async def _mark_accepted(
        self,
        *,
        proposal: AgentActionProposalRecord,
        submission: ActionSubmission,
        request: AgentActionProposalAcceptRequest,
    ) -> AgentActionProposalRecord:
        accepted = await self.store.mark_accepted(
            proposal_id=proposal.proposal_id,
            action_id=submission.action_id,
            accepted_by=request.accepted_by,
            reason=request.reason,
        )
        if accepted is None:
            raise AgentActionProposalStateError(
                f"Agent action proposal {proposal.proposal_id} could not be marked accepted"
            )
        return accepted

    async def _append_accept_thread_event(
        self,
        *,
        proposal: AgentActionProposalRecord,
        action_submission: ActionSubmission,
        request: AgentActionProposalAcceptRequest,
    ) -> None:
        if self.task_thread is None:
            return
        try:
            await self.task_thread.append_agent_reply(
                task_id=proposal.task_id,
                request=_accept_thread_request(proposal=proposal, action_submission=action_submission, request=request),
            )
        except Exception:  # pragma: no cover - observability must not break acceptance
            logger.exception(
                "failed to append agent proposal accept event to task thread",
                extra={"proposal_id": str(proposal.proposal_id), "task_id": str(proposal.task_id)},
            )


def _action_metadata(
    *,
    proposal: AgentActionProposalRecord,
    request: AgentActionProposalAcceptRequest,
) -> dict[str, Any]:
    return sanitize_json(
        {
            **request.metadata,
            "schema_version": AGENT_ACTION_PROPOSAL_ACCEPT_SCHEMA_VERSION,
            "source": "agent_action_proposal_accept",
            "agent_action_proposal": _proposal_metadata(proposal),
            "acceptance": {
                "accepted_by": request.accepted_by,
                "reason": request.reason,
                "boundary": {"agent_direct_execution": False, "submitted_through_action_service": True},
            },
        }
    )


def _proposal_metadata(proposal: AgentActionProposalRecord) -> dict[str, Any]:
    return {
        "proposal_id": str(proposal.proposal_id),
        "task_id": str(proposal.task_id),
        "source_message_id": str(proposal.source_message_id),
        "agent_key": proposal.agent_key,
        "proposal_type": proposal.proposal_type.value,
        "title": proposal.title,
    }


def _accept_thread_request(
    *,
    proposal: AgentActionProposalRecord,
    action_submission: ActionSubmission,
    request: AgentActionProposalAcceptRequest,
) -> AgentTaskAgentReplyRequest:
    status = action_submission.status.value
    return AgentTaskAgentReplyRequest(
        agent_key="proposal-feedback",
        body=_accept_thread_body(status),
        message_kind=AgentTaskMessageKind.DECISION,
        source="system",
        proposal_refs=[proposal_record_ref(proposal)],
        action_refs=[_action_ref(action_submission, status=status)],
        decision_refs=[_accept_decision_ref(proposal, action_submission, request=request)],
        metadata=_thread_metadata(event_type="proposal_accepted", source="agent_action_proposal_accept"),
    )


def _accept_thread_body(status: str) -> str:
    return (
        f"Предложение принято. Создан ActionRequest со статусом {status}. "
        "Дальше запуск всё равно проходит через ActionService, scope, policy, approval и budget."
    )


def _action_ref(action_submission: ActionSubmission, *, status: str) -> dict[str, Any]:
    return {
        "kind": "tool_action_request",
        "action_id": str(action_submission.action_id),
        "status": status,
        "campaign_id": str(action_submission.campaign_id) if action_submission.campaign_id else None,
    }


def _accept_decision_ref(
    proposal: AgentActionProposalRecord,
    action_submission: ActionSubmission,
    *,
    request: AgentActionProposalAcceptRequest,
) -> dict[str, Any]:
    return {
        "kind": "agent_action_proposal_decision",
        "decision": "accepted",
        "proposal_id": str(proposal.proposal_id),
        "action_id": str(action_submission.action_id),
        "actor": request.accepted_by,
        "confidence": request.confidence,
        "reason": request.reason,
    }


def _thread_metadata(*, event_type: str, source: str) -> dict[str, Any]:
    return {
        "schema_version": AGENT_ACTION_PROPOSAL_THREAD_EVENT_SCHEMA_VERSION,
        "source": source,
        "event_type": event_type,
        "decision": "accepted",
        "feedback_visible_in_live_thread": True,
        "boundary": {"agent_direct_execution": False, "submitted_through_action_service": True},
    }
