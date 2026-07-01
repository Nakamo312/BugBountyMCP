"""Postgres store for action-experience proposal acceptance/review state."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from api.application.action_experience_proposals import (
    ActionExperienceProposalRecord,
    ActionExperienceProposalReviewDecision,
    ActionExperienceProposalStatus,
    ActionExperienceProposalStore as ActionExperienceProposalStoreProtocol,
)
from api.infrastructure.action_experience_proposal_transactions import (
    get_proposal_in_session,
    mark_reviewed_in_session,
    transition_acceptance_in_session,
)


class ActionExperienceProposalStore(ActionExperienceProposalStoreProtocol):
    """Async SQLAlchemy adapter for graph-projector action-experience proposals."""

    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

    async def get_proposal(self, proposal_id: UUID) -> ActionExperienceProposalRecord | None:
        async with self.session_factory() as session:
            return await get_proposal_in_session(session, proposal_id)

    async def claim_acceptance(
        self,
        *,
        proposal_id: UUID,
        action_id: UUID,
        accepted_by: str,
        reason: str | None,
        confidence: float,
        metadata: dict[str, Any],
    ) -> ActionExperienceProposalRecord | None:
        return await self._transition_acceptance(
            proposal_id=proposal_id,
            from_status=ActionExperienceProposalStatus.PENDING,
            to_status=ActionExperienceProposalStatus.ACCEPTING,
            action_id=action_id,
            actor=accepted_by,
            reason=reason,
            confidence=confidence,
            metadata=metadata,
        )

    async def retry_acceptance(
        self,
        *,
        proposal_id: UUID,
        action_id: UUID,
        accepted_by: str,
        reason: str | None,
        confidence: float,
        metadata: dict[str, Any],
    ) -> ActionExperienceProposalRecord | None:
        return await self._transition_acceptance(
            proposal_id=proposal_id,
            from_status=ActionExperienceProposalStatus.ACCEPT_FAILED,
            to_status=ActionExperienceProposalStatus.ACCEPTING,
            action_id=action_id,
            actor=accepted_by,
            reason=reason,
            confidence=confidence,
            metadata=metadata,
        )

    async def mark_accepted(
        self,
        *,
        proposal_id: UUID,
        action_id: UUID,
        accepted_by: str,
        reason: str | None,
        confidence: float,
        metadata: dict[str, Any],
    ) -> ActionExperienceProposalRecord | None:
        return await self._transition_acceptance(
            proposal_id=proposal_id,
            from_status=ActionExperienceProposalStatus.ACCEPTING,
            to_status=ActionExperienceProposalStatus.ACCEPTED,
            action_id=action_id,
            actor=accepted_by,
            reason=reason,
            confidence=confidence,
            metadata=metadata,
        )

    async def mark_accept_failed(
        self,
        *,
        proposal_id: UUID,
        action_id: UUID,
        accepted_by: str,
        reason: str | None,
        confidence: float,
        metadata: dict[str, Any],
        error: str,
    ) -> ActionExperienceProposalRecord | None:
        return await self._transition_acceptance(
            proposal_id=proposal_id,
            from_status=ActionExperienceProposalStatus.ACCEPTING,
            to_status=ActionExperienceProposalStatus.ACCEPT_FAILED,
            action_id=action_id,
            actor=accepted_by,
            reason=reason,
            confidence=confidence,
            metadata=metadata,
            error=error,
        )

    async def _transition_acceptance(
        self,
        *,
        proposal_id: UUID,
        from_status: ActionExperienceProposalStatus,
        to_status: ActionExperienceProposalStatus,
        action_id: UUID,
        actor: str,
        reason: str | None,
        confidence: float,
        metadata: dict[str, Any],
        error: str | None = None,
    ) -> ActionExperienceProposalRecord | None:
        async with self.session_factory() as session:
            record = await transition_acceptance_in_session(
                session,
                proposal_id=proposal_id,
                from_status=from_status,
                to_status=to_status,
                action_id=action_id,
                actor=actor,
                reason=reason,
                confidence=confidence,
                metadata=metadata,
                error=error,
            )
            if record is not None and hasattr(session, "commit"):
                await session.commit()
            return record

    async def mark_reviewed(
        self,
        *,
        proposal_id: UUID,
        status: ActionExperienceProposalReviewDecision,
        reviewed_by: str,
        reason: str | None,
        confidence: float,
        metadata: dict[str, Any],
    ) -> ActionExperienceProposalRecord | None:
        async with self.session_factory() as session:
            record = await mark_reviewed_in_session(
                session,
                proposal_id=proposal_id,
                status=status,
                reviewed_by=reviewed_by,
                reason=reason,
                confidence=confidence,
                metadata=metadata,
            )
            if record is not None and hasattr(session, "commit"):
                await session.commit()
            return record
