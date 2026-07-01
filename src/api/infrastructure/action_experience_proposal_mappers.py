"""Mappers and audit payload builders for action-experience proposal state."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from api.application.action_experience_proposals import (
    ActionExperienceProposalRecord,
    ActionExperienceProposalReviewDecision,
    ActionExperienceProposalStatus,
)


def action_experience_proposal_record(row: dict[str, Any]) -> ActionExperienceProposalRecord:
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


def acceptance_payload(
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


def review_payload(
    *,
    status: ActionExperienceProposalReviewDecision,
    actor: str,
    reason: str | None,
    confidence: float,
    metadata: dict[str, Any],
    now,
) -> dict[str, Any]:
    return {
        "status": status.value,
        "actor": actor,
        "reason": reason,
        "confidence": max(0.0, min(1.0, float(confidence))),
        "source": "action-experience-proposal-review-service",
        "reviewed_at": now.isoformat(),
        "metadata": metadata,
    }
