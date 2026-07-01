"""SQLAlchemy transaction steps for action-experience proposals."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select, update

from api.application.action_experience_proposals import (
    ActionExperienceProposalRecord,
    ActionExperienceProposalReviewDecision,
    ActionExperienceProposalStatus,
)
from api.application.agent_tasks import utcnow
from api.infrastructure.action_experience_proposal_mappers import (
    acceptance_payload,
    action_experience_proposal_record,
    review_payload,
)
from api.infrastructure.adapters.orm import action_experience_proposals


async def get_proposal_in_session(session, proposal_id: UUID) -> ActionExperienceProposalRecord | None:
    result = await session.execute(select(action_experience_proposals).where(action_experience_proposals.c.id == proposal_id))
    row = result.mappings().one_or_none()
    if row is None:
        return None
    return action_experience_proposal_record(dict(row))


async def transition_acceptance_in_session(
    session,
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
    result = await session.execute(select(action_experience_proposals).where(action_experience_proposals.c.id == proposal_id))
    current_row = result.mappings().one_or_none()
    if current_row is None:
        return None
    current = dict(current_row)
    if current.get("status") != from_status.value:
        return None
    explanation = dict(current.get("explanation") or {})
    explanation["acceptance"] = acceptance_payload(
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
        .values(status=to_status.value, explanation=explanation, updated_at=now)
        .returning(action_experience_proposals)
    )
    update_result = await session.execute(statement)
    row = update_result.mappings().one_or_none()
    if row is None:
        return None
    return action_experience_proposal_record(dict(row))


async def mark_reviewed_in_session(
    session,
    *,
    proposal_id: UUID,
    status: ActionExperienceProposalReviewDecision,
    reviewed_by: str,
    reason: str | None,
    confidence: float,
    metadata: dict[str, Any],
) -> ActionExperienceProposalRecord | None:
    now = utcnow()
    result = await session.execute(select(action_experience_proposals).where(action_experience_proposals.c.id == proposal_id))
    current_row = result.mappings().one_or_none()
    if current_row is None:
        return None
    current = dict(current_row)
    if current.get("status") != ActionExperienceProposalStatus.PENDING.value:
        return None
    explanation = dict(current.get("explanation") or {})
    explanation["review"] = review_payload(
        status=status,
        actor=reviewed_by,
        reason=reason,
        confidence=confidence,
        metadata=metadata,
        now=now,
    )
    statement = (
        update(action_experience_proposals)
        .where(
            action_experience_proposals.c.id == proposal_id,
            action_experience_proposals.c.status == ActionExperienceProposalStatus.PENDING.value,
        )
        .values(status=status.value, explanation=explanation, updated_at=now)
        .returning(action_experience_proposals)
    )
    update_result = await session.execute(statement)
    row = update_result.mappings().one_or_none()
    if row is None:
        return None
    return action_experience_proposal_record(dict(row))
