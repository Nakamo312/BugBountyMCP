"""Writer service for agent-generated action proposals."""
from __future__ import annotations

from uuid import UUID

from .agent_action_proposal_feedback import apply_feedback_down_rank, proposal_feedback_decision
from .agent_action_proposal_models import (
    AgentActionProposalDraft,
    AgentActionProposalFeedbackSignal,
    AgentActionProposalRecord,
)
from .agent_action_proposal_payloads import _agent_key, proposal_write_from_draft
from .agent_action_proposal_ports import AgentActionProposalStore


class AgentActionProposalService:
    """Sanitize and store proposals emitted by agent runtimes."""

    def __init__(self, store: AgentActionProposalStore) -> None:
        self.store = store

    async def write_agent_task_proposals(
        self,
        *,
        program_id: UUID,
        campaign_id: UUID | None,
        task_id: UUID,
        source_message_id: UUID,
        agent_key: str,
        drafts: tuple[AgentActionProposalDraft, ...],
    ) -> tuple[AgentActionProposalRecord, ...]:
        records: list[AgentActionProposalRecord] = []
        normalized_agent_key = _agent_key(agent_key)
        feedback_signals = await self._recent_feedback_signals(
            program_id=program_id,
            campaign_id=campaign_id,
            agent_key=normalized_agent_key,
        )
        for index, draft in enumerate(drafts[:10], start=1):
            write = proposal_write_from_draft(
                program_id=program_id,
                campaign_id=campaign_id,
                task_id=task_id,
                source_message_id=source_message_id,
                agent_key=normalized_agent_key,
                draft=draft,
                index=index,
            )
            decision = proposal_feedback_decision(
                draft=write.draft,
                campaign_id=campaign_id,
                signals=feedback_signals,
            )
            if decision.is_suppressed:
                continue
            if decision.is_down_ranked:
                write = apply_feedback_down_rank(write, decision)
            records.append(await self.store.create_from_agent_task(proposal=write))
        return tuple(records)

    async def _recent_feedback_signals(
        self,
        *,
        program_id: UUID,
        campaign_id: UUID | None,
        agent_key: str,
    ) -> tuple[AgentActionProposalFeedbackSignal, ...]:
        reader = getattr(self.store, "list_recent_review_feedback", None)
        if reader is None:
            return tuple()
        return await reader(
            program_id=program_id,
            campaign_id=campaign_id,
            agent_key=agent_key,
            limit=50,
        )
