"""Ports used by agent action proposal application services."""
from __future__ import annotations

from typing import Protocol
from uuid import UUID

from api.application.agent_tasks import AgentTaskAgentReplyRequest, AgentTaskMessageRecord
from api.application.contracts import ActionRequest, ActionSubmission

from .agent_action_proposal_models import (
    AgentActionProposalFeedbackSignal,
    AgentActionProposalRecord,
    AgentActionProposalReviewDecision,
    AgentActionProposalDraft,
    AgentActionProposalWrite,
)


class AgentActionProposalStore(Protocol):
    async def create_from_agent_task(
        self,
        *,
        proposal: AgentActionProposalWrite,
    ) -> AgentActionProposalRecord: ...

    async def list_recent_review_feedback(
        self,
        *,
        program_id: UUID,
        campaign_id: UUID | None,
        agent_key: str,
        limit: int = 50,
    ) -> tuple[AgentActionProposalFeedbackSignal, ...]: ...

    async def get_proposal(self, proposal_id: UUID) -> AgentActionProposalRecord | None: ...

    async def mark_accepted(
        self,
        *,
        proposal_id: UUID,
        action_id: UUID,
        accepted_by: str,
        reason: str | None,
    ) -> AgentActionProposalRecord | None: ...

    async def mark_reviewed(
        self,
        *,
        proposal_id: UUID,
        decision: AgentActionProposalReviewDecision,
        reviewed_by: str,
        reason: str | None,
        confidence: float,
        feedback_tags: list[str],
        metadata: dict[str, object],
    ) -> AgentActionProposalRecord | None: ...


class ActionRequestSubmitter(Protocol):
    async def request_action(
        self,
        action: ActionRequest,
        *,
        confidence: float = 0.5,
    ) -> ActionSubmission: ...


class ActionCatalogResolver(Protocol):
    async def find_detail(self, *, capability: str, profile: str): ...


class AgentTaskThreadWriter(Protocol):
    async def append_agent_reply(
        self,
        *,
        task_id: UUID,
        request: AgentTaskAgentReplyRequest,
    ) -> AgentTaskMessageRecord: ...


class AgentActionProposalWriter(Protocol):
    async def write_agent_task_proposals(
        self,
        *,
        program_id: UUID,
        campaign_id: UUID | None,
        task_id: UUID,
        source_message_id: UUID,
        agent_key: str,
        drafts: tuple[AgentActionProposalDraft, ...],
    ) -> tuple[AgentActionProposalRecord, ...]: ...
