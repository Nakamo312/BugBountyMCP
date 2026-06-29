"""Postgres store for action-experience proposal acceptance."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select, update

from api.application.action_experience_proposals import (
    ActionExperienceProposalRecord,
    ActionExperienceProposalReviewDecision,
    ActionExperienceProposalStatus,
    ActionExperienceProposalStore as ActionExperienceProposalStoreProtocol,
)
from api.application.agent_tasks import utcnow
from api.infrastructure.adapters.orm import action_experience_proposals


class ActionExperienceProposalStore(ActionExperienceProposalStoreProtocol):
    """Async SQLAlchemy adapter for graph-projector action-experience proposals."""

    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

    async def get_proposal(self, proposal_id: UUID) -> ActionExperienceProposalRecord | None:
        async with self.session_factory() as session:
            result = await session.execute(
                select(action_experience_proposals).where(action_experience_proposals.c.id == proposal_id)
            )
            row = result.mappings().one_or_none()
        if row is None:
            return None
        return self._record(dict(row))

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
        now = utcnow()
        async with self.session_factory() as session:
            result = await session.execute(
                select(action_experience_proposals).where(action_experience_proposals.c.id == proposal_id)
            )
            current_row = result.mappings().one_or_none()
            if current_row is None:
                return None
            current = dict(current_row)
            if current.get("status") != from_status.value:
                return None
            explanation = dict(current.get("explanation") or {})
            explanation["acceptance"] = _acceptance_payload(
                status=to_status,
                action_id=action_id,
                actor=actor,
                reason=reason,
                confidence=confidence,
                metadata=metadata,
                now=now,
                error=error,
            )
            statement = (
                update(action_experience_proposals)
                .where(
                    action_experience_proposals.c.id == proposal_id,
                    action_experience_proposals.c.status == from_status.value,
                )
                .values(
                    status=to_status.value,
                    explanation=explanation,
                    updated_at=now,
                )
                .returning(action_experience_proposals)
            )
            update_result = await session.execute(statement)
            row = update_result.mappings().one_or_none()
            if row is None:
                return None
            accepted = dict(row)
            if hasattr(session, "commit"):
                await session.commit()
        return self._record(accepted)

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
        now = utcnow()
        async with self.session_factory() as session:
            result = await session.execute(
                select(action_experience_proposals).where(action_experience_proposals.c.id == proposal_id)
            )
            current_row = result.mappings().one_or_none()
            if current_row is None:
                return None
            current = dict(current_row)
            if current.get("status") != ActionExperienceProposalStatus.PENDING.value:
                return None
            explanation = dict(current.get("explanation") or {})
            explanation["review"] = {
                "status": status.value,
                "actor": reviewed_by,
                "reason": reason,
                "confidence": max(0.0, min(1.0, float(confidence))),
                "source": "action-experience-proposal-review-service",
                "reviewed_at": now.isoformat(),
                "metadata": metadata,
            }
            statement = (
                update(action_experience_proposals)
                .where(
                    action_experience_proposals.c.id == proposal_id,
                    action_experience_proposals.c.status == ActionExperienceProposalStatus.PENDING.value,
                )
                .values(
                    status=status.value,
                    explanation=explanation,
                    updated_at=now,
                )
                .returning(action_experience_proposals)
            )
            update_result = await session.execute(statement)
            row = update_result.mappings().one_or_none()
            if row is None:
                return None
            reviewed = dict(row)
            if hasattr(session, "commit"):
                await session.commit()
        return self._record(reviewed)

    @staticmethod
    def _record(row: dict[str, Any]) -> ActionExperienceProposalRecord:
        return ActionExperienceProposalRecord(
            proposal_id=row["id"],
            proposal_run_id=row["proposal_run_id"],
            program_id=row["program_id"],
            campaign_id=row.get("campaign_id"),
            source_outcome_id=row["source_outcome_id"],
            source_action_id=row["source_action_id"],
            source_job_id=row["source_job_id"],
            source_run_id=row["source_run_id"],
            proposal_key=row["proposal_key"],
            status=row["status"],
            rank=int(row["rank"]),
            capability_id=row["capability_id"],
            profile_id=row["profile_id"],
            utility_score=float(row.get("utility_score") or 0.0),
            sample_count=int(row.get("sample_count") or 0),
            avg_similarity=float(row.get("avg_similarity") or 0.0),
            avg_information_gain_score=float(row.get("avg_information_gain_score") or 0.0),
            human_positive_rate=float(row.get("human_positive_rate") or 0.0),
            human_stop_rate=float(row.get("human_stop_rate") or 0.0),
            explanation=row.get("explanation") or {},
            produced_by=row["produced_by"],
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )


def _acceptance_payload(
    *,
    status: ActionExperienceProposalStatus,
    action_id: UUID,
    actor: str,
    reason: str | None,
    confidence: float,
    metadata: dict[str, Any],
    now,
    error: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": status.value,
        "accepted_by": actor,
        "reason": reason,
        "confidence": max(0.0, min(1.0, float(confidence))),
        "accepted_action_id": str(action_id),
        "source": "action-experience-proposal-acceptance-service",
        "accepted_at": now.isoformat(),
        "metadata": metadata,
    }
    if error is not None:
        payload["error"] = error
    return payload
