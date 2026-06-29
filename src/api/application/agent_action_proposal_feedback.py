"""Feedback policy for newly generated agent action proposals."""
from __future__ import annotations

from dataclasses import replace
from typing import Any
from uuid import UUID

from api.application.research.sanitizer import sanitize_json, sanitize_text

from .agent_action_proposal_models import (
    AGENT_ACTION_PROPOSAL_FEEDBACK_POLICY_VERSION,
    AgentActionProposalDraft,
    AgentActionProposalFeedbackDecision,
    AgentActionProposalFeedbackSignal,
    AgentActionProposalReviewDecision,
    AgentActionProposalWrite,
)


def proposal_feedback_decision(
    *,
    draft: AgentActionProposalDraft,
    campaign_id: UUID | None,
    signals: tuple[AgentActionProposalFeedbackSignal, ...],
) -> AgentActionProposalFeedbackDecision:
    """Apply conservative negative-feedback matching to a new draft."""

    best_suppress = _best_feedback_match(
        draft=draft,
        campaign_id=campaign_id,
        signals=signals,
        decision=AgentActionProposalReviewDecision.SUPPRESSED,
        threshold=0.55,
    )
    if best_suppress is not None:
        return _feedback_decision("suppress", best_suppress)
    best_reject = _best_feedback_match(
        draft=draft,
        campaign_id=campaign_id,
        signals=signals,
        decision=AgentActionProposalReviewDecision.REJECTED,
        threshold=0.35,
    )
    if best_reject is not None:
        return _feedback_decision("down_rank", best_reject)
    return AgentActionProposalFeedbackDecision(action="allow")


def apply_feedback_down_rank(
    write: AgentActionProposalWrite,
    decision: AgentActionProposalFeedbackDecision,
) -> AgentActionProposalWrite:
    signal = decision.signal
    if signal is None:
        return write
    metadata = sanitize_json(
        {
            **write.metadata,
            "feedback_policy": {
                "policy": AGENT_ACTION_PROPOSAL_FEEDBACK_POLICY_VERSION,
                "decision": "down_ranked_due_to_prior_rejection",
                "matched_feedback_type": signal.feedback_type.value,
                "matched_proposal_id": str(signal.proposal_id),
                "match_score": decision.match_score,
                "confidence": signal.confidence,
                "feedback_tags": list(signal.feedback_tags),
                "reason_excerpt": sanitize_text(signal.reason or "", limit=300).safe_excerpt,
            },
        }
    )
    draft = write.draft.model_copy(update={"priority": _lower_priority(write.draft.priority), "metadata": metadata})
    return replace(write, draft=draft, metadata=metadata)


def _best_feedback_match(
    *,
    draft: AgentActionProposalDraft,
    campaign_id: UUID | None,
    signals: tuple[AgentActionProposalFeedbackSignal, ...],
    decision: AgentActionProposalReviewDecision,
    threshold: float,
) -> tuple[float, AgentActionProposalFeedbackSignal] | None:
    best: tuple[float, AgentActionProposalFeedbackSignal] | None = None
    for signal in signals:
        if signal.feedback_type is not decision:
            continue
        weighted = _feedback_match_score(draft=draft, signal=signal, campaign_id=campaign_id)
        weighted *= max(0.0, min(1.0, signal.confidence))
        if weighted >= threshold and (best is None or weighted > best[0]):
            best = (weighted, signal)
    return best


def _feedback_decision(
    action: str,
    match: tuple[float, AgentActionProposalFeedbackSignal],
) -> AgentActionProposalFeedbackDecision:
    return AgentActionProposalFeedbackDecision(
        action=action,
        match_score=round(match[0], 4),
        signal=match[1],
    )


def _feedback_match_score(
    *,
    draft: AgentActionProposalDraft,
    signal: AgentActionProposalFeedbackSignal,
    campaign_id: UUID | None,
) -> float:
    score = 0.0
    if draft.proposal_type is signal.proposal_type:
        score += 0.10
    if _same_text(draft.action_intent, signal.action_intent):
        score += 0.35
    score += _capability_profile_match_score(draft, signal)
    score += min(0.20, 0.20 * _token_overlap(draft.title, signal.title))
    score += min(0.10, 0.10 * _context_kind_overlap(draft.context_refs, signal.context_refs))
    if campaign_id is not None and signal.campaign_id == campaign_id:
        score += 0.10
    elif signal.campaign_id is None:
        score += 0.03
    return min(1.0, score)


def _capability_profile_match_score(
    draft: AgentActionProposalDraft,
    signal: AgentActionProposalFeedbackSignal,
) -> float:
    capability_match = _same_text(draft.capability_id, signal.capability_id)
    profile_match = _same_text(draft.profile_id, signal.profile_id)
    if capability_match and profile_match:
        return 0.30
    if capability_match or profile_match:
        return 0.15
    return 0.0


def _same_text(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False
    return str(left).strip().lower() == str(right).strip().lower()


def _token_overlap(left: str | None, right: str | None) -> float:
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens))


def _tokens(value: str | None) -> set[str]:
    if not value:
        return set()
    return {
        token
        for token in "".join(ch.lower() if ch.isalnum() else " " for ch in str(value)).split()
        if len(token) >= 3
    }


def _context_kind_overlap(
    left: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    right: list[dict[str, Any]] | tuple[dict[str, Any], ...],
) -> float:
    left_kinds = {str(item.get("kind") or item.get("type") or "") for item in left if isinstance(item, dict)}
    right_kinds = {str(item.get("kind") or item.get("type") or "") for item in right if isinstance(item, dict)}
    left_kinds.discard("")
    right_kinds.discard("")
    if not left_kinds or not right_kinds:
        return 0.0
    return len(left_kinds & right_kinds) / max(1, len(left_kinds | right_kinds))


def _lower_priority(value: str | None) -> str:
    normalized = str(value or "medium").strip().lower()
    if normalized in {"critical", "high"}:
        return "medium"
    if normalized == "medium":
        return "low"
    return normalized or "low"
