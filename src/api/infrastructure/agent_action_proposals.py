"""Postgres store for bounded agent action proposals."""
from __future__ import annotations

from typing import Any

from sqlalchemy import desc, select, update
from sqlalchemy.dialects.postgresql import insert

from api.application.agent_action_proposals import (
    AgentActionProposalFeedbackSignal,
    AgentActionProposalRecord,
    AgentActionProposalReviewDecision,
    AgentActionProposalStatus,
    AgentActionProposalType,
    AgentActionProposalStore as AgentActionProposalStoreProtocol,
    AgentActionProposalWrite,
)
from api.application.agent_tasks import utcnow
from api.infrastructure.adapters.orm import agent_action_proposal_feedback_events, agent_action_proposals


class AgentActionProposalStore(AgentActionProposalStoreProtocol):
    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

    async def create_from_agent_task(
        self,
        *,
        proposal: AgentActionProposalWrite,
    ) -> AgentActionProposalRecord:
        values = {
            "id": proposal.proposal_id,
            "program_id": proposal.program_id,
            "campaign_id": proposal.campaign_id,
            "task_id": proposal.task_id,
            "source_message_id": proposal.source_message_id,
            "agent_key": proposal.agent_key,
            "proposal_key": proposal.proposal_key,
            "proposal_type": proposal.draft.proposal_type.value,
            "status": AgentActionProposalStatus.PENDING.value,
            "title": proposal.title,
            "summary": proposal.summary,
            "rationale": proposal.rationale,
            "capability_id": proposal.draft.capability_id,
            "profile_id": proposal.draft.profile_id,
            "priority": proposal.draft.priority or "medium",
            "risk_level": proposal.draft.risk_level or "low",
            "expected_gain": proposal.draft.expected_gain or "",
            "action_intent": proposal.draft.action_intent or "",
            "action_params": proposal.draft.action_params,
            "context_refs": proposal.context_refs,
            "metadata": proposal.metadata,
            "produced_by": "agent-task-runtime",
        }
        statement = (
            insert(agent_action_proposals)
            .values(**values)
            .on_conflict_do_update(
                index_elements=["proposal_key"],
                set_={
                    "title": values["title"],
                    "summary": values["summary"],
                    "rationale": values["rationale"],
                    "priority": values["priority"],
                    "risk_level": values["risk_level"],
                    "expected_gain": values["expected_gain"],
                    "action_intent": values["action_intent"],
                    "action_params": values["action_params"],
                    "context_refs": values["context_refs"],
                    "metadata": values["metadata"],
                    "updated_at": agent_action_proposals.c.updated_at,
                },
            )
            .returning(agent_action_proposals)
        )
        async with self.session_factory() as session:
            result = await session.execute(statement)
            if hasattr(session, "commit"):
                await session.commit()
            row = dict(result.mappings().one())
        return self._record(row)

    async def list_recent_review_feedback(
        self,
        *,
        program_id,
        campaign_id,
        agent_key: str,
        limit: int = 50,
    ) -> tuple[AgentActionProposalFeedbackSignal, ...]:
        statement = (
            select(
                agent_action_proposal_feedback_events.c.proposal_id,
                agent_action_proposal_feedback_events.c.campaign_id,
                agent_action_proposal_feedback_events.c.agent_key,
                agent_action_proposal_feedback_events.c.feedback_type,
                agent_action_proposal_feedback_events.c.confidence,
                agent_action_proposal_feedback_events.c.feedback_tags,
                agent_action_proposal_feedback_events.c.reason,
                agent_action_proposal_feedback_events.c.created_at,
                agent_action_proposals.c.proposal_type,
                agent_action_proposals.c.title,
                agent_action_proposals.c.capability_id,
                agent_action_proposals.c.profile_id,
                agent_action_proposals.c.action_intent,
                agent_action_proposals.c.context_refs,
            )
            .select_from(
                agent_action_proposal_feedback_events.join(
                    agent_action_proposals,
                    agent_action_proposal_feedback_events.c.proposal_id == agent_action_proposals.c.id,
                )
            )
            .where(agent_action_proposal_feedback_events.c.program_id == program_id)
            .where(agent_action_proposal_feedback_events.c.agent_key == agent_key)
            .order_by(desc(agent_action_proposal_feedback_events.c.created_at))
            .limit(max(1, min(int(limit or 50), 200)))
        )
        async with self.session_factory() as session:
            result = await session.execute(statement)
            rows = [dict(row) for row in result.mappings().all()]
        return tuple(_feedback_signal(row) for row in rows)

    async def get_proposal(self, proposal_id) -> AgentActionProposalRecord | None:
        statement = select(agent_action_proposals).where(agent_action_proposals.c.id == proposal_id)
        async with self.session_factory() as session:
            result = await session.execute(statement)
            row = result.mappings().one_or_none()
        return self._record(dict(row)) if row is not None else None

    async def mark_accepted(
        self,
        *,
        proposal_id,
        action_id,
        accepted_by: str,
        reason: str | None,
    ) -> AgentActionProposalRecord | None:
        statement = (
            update(agent_action_proposals)
            .where(
                agent_action_proposals.c.id == proposal_id,
                agent_action_proposals.c.status == AgentActionProposalStatus.PENDING.value,
            )
            .values(
                status=AgentActionProposalStatus.ACCEPTED.value,
                accepted_action_id=action_id,
                accepted_by=accepted_by,
                accepted_reason=reason,
                accepted_at=utcnow(),
                updated_at=utcnow(),
            )
            .returning(agent_action_proposals)
        )
        async with self.session_factory() as session:
            result = await session.execute(statement)
            row = result.mappings().one_or_none()
            if row is not None and hasattr(session, "commit"):
                await session.commit()
        return self._record(dict(row)) if row is not None else None

    async def mark_reviewed(
        self,
        *,
        proposal_id,
        decision: AgentActionProposalReviewDecision,
        reviewed_by: str,
        reason: str | None,
        confidence: float,
        feedback_tags: list[str],
        metadata: dict[str, Any],
    ) -> AgentActionProposalRecord | None:
        now = utcnow()
        feedback = {
            "confidence": confidence,
            "feedback_tags": feedback_tags,
            **metadata,
        }
        async with self.session_factory() as session:
            current_result = await session.execute(
                select(agent_action_proposals).where(agent_action_proposals.c.id == proposal_id)
            )
            current_row = current_result.mappings().one_or_none()
            if current_row is None:
                return None
            current = dict(current_row)
            if current.get("status") != AgentActionProposalStatus.PENDING.value:
                return None

            statement = (
                update(agent_action_proposals)
                .where(
                    agent_action_proposals.c.id == proposal_id,
                    agent_action_proposals.c.status == AgentActionProposalStatus.PENDING.value,
                )
                .values(
                    status=decision.value,
                    reviewed_by=reviewed_by,
                    review_reason=reason,
                    review_feedback=feedback,
                    reviewed_at=now,
                    updated_at=now,
                )
                .returning(agent_action_proposals)
            )
            result = await session.execute(statement)
            row = result.mappings().one_or_none()
            if row is None:
                return None
            reviewed = dict(row)
            await session.execute(
                insert(agent_action_proposal_feedback_events).values(
                    proposal_id=proposal_id,
                    program_id=current["program_id"],
                    campaign_id=current.get("campaign_id"),
                    task_id=current["task_id"],
                    source_message_id=current["source_message_id"],
                    agent_key=current["agent_key"],
                    previous_status=current["status"],
                    new_status=decision.value,
                    feedback_type=decision.value,
                    actor=reviewed_by,
                    reason=reason,
                    confidence=confidence,
                    feedback_tags=feedback_tags,
                    metadata=feedback,
                    created_at=now,
                )
            )
            if hasattr(session, "commit"):
                await session.commit()
        return self._record(reviewed)

    @staticmethod
    def _record(row: dict[str, Any]) -> AgentActionProposalRecord:
        return AgentActionProposalRecord(
            proposal_id=row["id"],
            program_id=row["program_id"],
            campaign_id=row.get("campaign_id"),
            task_id=row["task_id"],
            source_message_id=row["source_message_id"],
            agent_key=row["agent_key"],
            proposal_key=row["proposal_key"],
            proposal_type=row["proposal_type"],
            status=row["status"],
            title=row["title"],
            summary=row["summary"],
            rationale=row.get("rationale") or "",
            capability_id=row.get("capability_id"),
            profile_id=row.get("profile_id"),
            priority=row["priority"],
            risk_level=row["risk_level"],
            expected_gain=row.get("expected_gain") or "",
            action_intent=row.get("action_intent") or "",
            action_params=row.get("action_params") or {},
            context_refs=row.get("context_refs") or [],
            metadata=row.get("metadata") or {},
            produced_by=row["produced_by"],
            accepted_action_id=row.get("accepted_action_id"),
            accepted_by=row.get("accepted_by"),
            accepted_reason=row.get("accepted_reason"),
            accepted_at=row.get("accepted_at"),
            reviewed_by=row.get("reviewed_by"),
            review_reason=row.get("review_reason"),
            review_feedback=row.get("review_feedback") or {},
            reviewed_at=row.get("reviewed_at"),
        )


def _feedback_signal(row: dict[str, Any]) -> AgentActionProposalFeedbackSignal:
    return AgentActionProposalFeedbackSignal(
        proposal_id=row["proposal_id"],
        campaign_id=row.get("campaign_id"),
        agent_key=row["agent_key"],
        proposal_type=AgentActionProposalType(row["proposal_type"]),
        feedback_type=AgentActionProposalReviewDecision(row["feedback_type"]),
        confidence=float(row.get("confidence") or 0.0),
        title=row.get("title") or "",
        capability_id=row.get("capability_id"),
        profile_id=row.get("profile_id"),
        action_intent=row.get("action_intent") or "",
        context_refs=tuple(row.get("context_refs") or ()),
        feedback_tags=tuple(row.get("feedback_tags") or ()),
        reason=row.get("reason"),
        created_at=row.get("created_at"),
    )
