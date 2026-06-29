"""Review service for stored agent action proposals."""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from api.application.agent_tasks import AgentTaskAgentReplyRequest, AgentTaskMessageKind
from api.application.research.sanitizer import sanitize_json

from .agent_action_proposal_models import (
    AGENT_ACTION_PROPOSAL_REVIEW_SCHEMA_VERSION,
    AGENT_ACTION_PROPOSAL_THREAD_EVENT_SCHEMA_VERSION,
    AgentActionProposalNotFound,
    AgentActionProposalRecord,
    AgentActionProposalReviewDecision,
    AgentActionProposalReviewRequest,
    AgentActionProposalReviewResult,
    AgentActionProposalStateError,
    AgentActionProposalStatus,
)
from .agent_action_proposal_payloads import proposal_record_ref
from .agent_action_proposal_ports import AgentActionProposalStore, AgentTaskThreadWriter

logger = logging.getLogger(__name__)


class AgentActionProposalReviewService:
    """Record negative feedback for stored agent proposals."""

    def __init__(
        self,
        *,
        store: AgentActionProposalStore,
        task_thread: AgentTaskThreadWriter | None = None,
    ) -> None:
        self.store = store
        self.task_thread = task_thread

    async def review(
        self,
        *,
        proposal_id: UUID,
        decision: AgentActionProposalReviewDecision,
        request: AgentActionProposalReviewRequest,
    ) -> AgentActionProposalReviewResult:
        proposal = await self._load_pending_proposal(proposal_id)
        reviewed = await self.store.mark_reviewed(
            proposal_id=proposal.proposal_id,
            decision=decision,
            reviewed_by=request.reviewed_by,
            reason=request.reason,
            confidence=request.confidence,
            feedback_tags=request.feedback_tags,
            metadata=_review_metadata(decision=decision, request=request),
        )
        if reviewed is None:
            raise AgentActionProposalStateError(
                f"Agent action proposal {proposal_id} could not be marked {decision.value}"
            )
        await self._append_review_thread_event(proposal=reviewed, decision=decision, request=request)
        return AgentActionProposalReviewResult(proposal=reviewed, decision=decision)

    async def _load_pending_proposal(self, proposal_id: UUID) -> AgentActionProposalRecord:
        proposal = await self.store.get_proposal(proposal_id)
        if proposal is None:
            raise AgentActionProposalNotFound(f"Agent action proposal not found: {proposal_id}")
        if proposal.status is not AgentActionProposalStatus.PENDING:
            raise AgentActionProposalStateError(
                f"Agent action proposal {proposal_id} is not pending: {proposal.status.value}"
            )
        return proposal

    async def _append_review_thread_event(
        self,
        *,
        proposal: AgentActionProposalRecord,
        decision: AgentActionProposalReviewDecision,
        request: AgentActionProposalReviewRequest,
    ) -> None:
        if self.task_thread is None:
            return
        try:
            await self.task_thread.append_agent_reply(
                task_id=proposal.task_id,
                request=_review_thread_request(proposal=proposal, decision=decision, request=request),
            )
        except Exception:  # pragma: no cover - observability must not break review
            logger.exception(
                "failed to append agent proposal review event to task thread",
                extra={"proposal_id": str(proposal.proposal_id), "task_id": str(proposal.task_id)},
            )


def _review_metadata(
    *,
    decision: AgentActionProposalReviewDecision,
    request: AgentActionProposalReviewRequest,
) -> dict[str, Any]:
    return sanitize_json(
        {
            **request.metadata,
            "schema_version": AGENT_ACTION_PROPOSAL_REVIEW_SCHEMA_VERSION,
            "source": "agent_action_proposal_review",
            "decision": decision.value,
            "feedback_boundary": {
                "agent_direct_execution": False,
                "proposal_deleted": False,
                "feeds_future_ranking": True,
            },
        }
    )


def _review_thread_request(
    *,
    proposal: AgentActionProposalRecord,
    decision: AgentActionProposalReviewDecision,
    request: AgentActionProposalReviewRequest,
) -> AgentTaskAgentReplyRequest:
    return AgentTaskAgentReplyRequest(
        agent_key="proposal-feedback",
        body=_review_body(decision=decision, request=request),
        message_kind=AgentTaskMessageKind.DECISION,
        source="system",
        proposal_refs=[proposal_record_ref(proposal)],
        decision_refs=[_review_decision_ref(proposal=proposal, decision=decision, request=request)],
        metadata=_review_thread_metadata(decision),
    )


def _review_body(
    *,
    decision: AgentActionProposalReviewDecision,
    request: AgentActionProposalReviewRequest,
) -> str:
    if decision is AgentActionProposalReviewDecision.SUPPRESSED:
        body = (
            "Предложение подавлено как обучающий сигнал. "
            "Похожие предложения будут отфильтровываться без нового сильного основания."
        )
    else:
        body = (
            "Предложение отклонено как обратная связь. "
            "Похожие предложения будут показываться осторожнее и с более низким приоритетом."
        )
    return f"{body} Причина: {request.reason}" if request.reason else body


def _review_decision_ref(
    *,
    proposal: AgentActionProposalRecord,
    decision: AgentActionProposalReviewDecision,
    request: AgentActionProposalReviewRequest,
) -> dict[str, Any]:
    return {
        "kind": "agent_action_proposal_decision",
        "decision": decision.value,
        "proposal_id": str(proposal.proposal_id),
        "actor": request.reviewed_by,
        "confidence": request.confidence,
        "reason": request.reason,
        "feedback_tags": request.feedback_tags,
    }


def _review_thread_metadata(decision: AgentActionProposalReviewDecision) -> dict[str, Any]:
    return {
        "schema_version": AGENT_ACTION_PROPOSAL_THREAD_EVENT_SCHEMA_VERSION,
        "source": "agent_action_proposal_review",
        "event_type": f"proposal_{decision.value}",
        "decision": decision.value,
        "feedback_visible_in_live_thread": True,
        "feedback_boundary": {
            "agent_direct_execution": False,
            "proposal_deleted": False,
            "feeds_future_ranking": True,
        },
    }
