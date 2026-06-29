from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping

from .action_experience_probe import ActionExperienceProbeRanking
from .action_outcome_gds import ActionOutcomeGdsCandidate
from .surface_gds import SurfaceComponentActionCandidate
from .proposal_row_codec import _required_text


REVIEW_PRIOR_FORMULA_VERSION = "action-experience-review-prior.v1"


@dataclass(frozen=True)
class ActionExperienceProposalReviewPrior:
    capability_id: str
    profile_id: str
    accepted_count: int = 0
    rejected_count: int = 0
    suppressed_count: int = 0
    accepted_confidence: float = 0.0
    rejected_confidence: float = 0.0
    suppressed_confidence: float = 0.0

    @property
    def review_count(self) -> int:
        return self.accepted_count + self.rejected_count + self.suppressed_count

    @property
    def positive_rate(self) -> float:
        if self.review_count <= 0:
            return 0.0
        return min(1.0, self.accepted_confidence / float(self.review_count))

    @property
    def stop_rate(self) -> float:
        if self.review_count <= 0:
            return 0.0
        weighted_stop = self.rejected_confidence + (1.5 * self.suppressed_confidence)
        return min(1.0, weighted_stop / float(self.review_count))

    @property
    def confidence(self) -> float:
        if self.review_count <= 0:
            return 0.0
        return float(self.review_count) / (float(self.review_count) + 5.0)

    @property
    def multiplier(self) -> float:
        if self.review_count <= 0:
            return 1.0
        positive = 1.0 + (0.35 * self.positive_rate * self.confidence)
        stop = 1.0 + (1.25 * self.stop_rate * self.confidence)
        return max(0.05, positive / stop)

    def as_explanation(self) -> dict[str, object]:
        return {
            "formula_version": REVIEW_PRIOR_FORMULA_VERSION,
            "accepted_count": self.accepted_count,
            "rejected_count": self.rejected_count,
            "suppressed_count": self.suppressed_count,
            "positive_rate": self.positive_rate,
            "stop_rate": self.stop_rate,
            "confidence": self.confidence,
            "multiplier": self.multiplier,
        }

def _review_prior_from_row(row: Mapping[str, Any]) -> ActionExperienceProposalReviewPrior:
    return ActionExperienceProposalReviewPrior(
        capability_id=str(row["capability_id"]),
        profile_id=str(row["profile_id"]),
        accepted_count=int(row.get("accepted_count") or 0),
        rejected_count=int(row.get("rejected_count") or 0),
        suppressed_count=int(row.get("suppressed_count") or 0),
        accepted_confidence=float(row.get("accepted_confidence") or 0.0),
        rejected_confidence=float(row.get("rejected_confidence") or 0.0),
        suppressed_confidence=float(row.get("suppressed_confidence") or 0.0),
    )


def _review_prior_for_candidate(
    review_priors: Mapping[tuple[str, str], ActionExperienceProposalReviewPrior] | None,
    capability_id: str,
    profile_id: str,
) -> ActionExperienceProposalReviewPrior | None:
    if not review_priors:
        return None
    return review_priors.get((capability_id, profile_id))


def _apply_review_prior_to_score(score: float, prior: ActionExperienceProposalReviewPrior | None) -> float:
    if prior is None:
        return max(0.0, float(score))
    return max(0.0, float(score) * prior.multiplier)


def _review_prior_explanation(prior: ActionExperienceProposalReviewPrior | None) -> dict[str, object]:
    if prior is None or prior.review_count <= 0:
        return {}
    return {"proposal_review_prior": prior.as_explanation()}




def _action_candidate_rank_score(candidate: ActionOutcomeGdsCandidate) -> float:
    return float(candidate.rank_score if candidate.rank_score is not None else candidate.utility_score)


def _ranked_action_candidates_with_review_priors(
    candidates: tuple[ActionOutcomeGdsCandidate, ...],
    review_priors: Mapping[tuple[str, str], ActionExperienceProposalReviewPrior] | None,
) -> tuple[ActionOutcomeGdsCandidate, ...]:
    if not review_priors:
        return candidates
    adjusted = tuple(
        _apply_review_prior_to_action_candidate(candidate, review_priors)
        for candidate in candidates
    )
    return tuple(sorted(adjusted, key=lambda item: (_action_candidate_rank_score(item), item.sample_count), reverse=True))

def _apply_review_priors_to_ranking(
    ranking: ActionExperienceProbeRanking,
    review_priors: Mapping[tuple[str, str], ActionExperienceProposalReviewPrior],
) -> ActionExperienceProbeRanking:
    if not review_priors:
        return ranking
    adjusted = tuple(
        _apply_review_prior_to_action_candidate(candidate, review_priors)
        for candidate in ranking.candidates
    )
    return ActionExperienceProbeRanking(
        feature_set=ranking.feature_set,
        candidates=tuple(
            sorted(adjusted, key=lambda item: (_action_candidate_rank_score(item), item.sample_count), reverse=True)
        ),
    )


def _apply_review_prior_to_action_candidate(
    candidate: ActionOutcomeGdsCandidate,
    review_priors: Mapping[tuple[str, str], ActionExperienceProposalReviewPrior],
) -> ActionOutcomeGdsCandidate:
    prior = _review_prior_for_candidate(review_priors, candidate.capability_id, candidate.profile_id)
    if prior is None:
        return candidate
    base_utility = float(candidate.base_utility_score if candidate.base_utility_score is not None else candidate.utility_score)
    adjusted_rank_score = _apply_review_prior_to_score(base_utility, prior)
    return replace(
        candidate,
        rank_score=adjusted_rank_score,
        base_utility_score=base_utility,
        adjusted_rank_score=adjusted_rank_score,
        review_prior_multiplier=prior.multiplier,
        review_prior_formula_version=REVIEW_PRIOR_FORMULA_VERSION,
        rank_score_semantics=(
            "operator-review-prior-adjusted rank score; "
            "utility_score remains outcome-derived historical utility"
        ),
    )


def _apply_review_priors_to_surface_candidates(
    candidates: tuple[SurfaceComponentActionCandidate, ...],
    review_priors: Mapping[tuple[str, str], ActionExperienceProposalReviewPrior],
) -> tuple[SurfaceComponentActionCandidate, ...]:
    if not review_priors:
        return candidates
    adjusted = tuple(
        _apply_review_prior_to_surface_candidate(candidate, review_priors)
        for candidate in candidates
    )
    return tuple(
        sorted(
            adjusted,
            key=lambda item: (
                item.candidate_score,
                item.component_attention_score,
                item.utility_score,
                item.sample_count,
            ),
            reverse=True,
        )
    )


def _score_features_after_review_prior(
    *,
    score_features: Mapping[str, object] | None,
    base_candidate_score: int,
    adjusted_candidate_score: int,
    prior: ActionExperienceProposalReviewPrior,
) -> dict[str, object]:
    features = dict(score_features or {})
    features.update(
        {
            "score_features_stage": "post_review_prior",
            "base_candidate_score": int(base_candidate_score),
            "adjusted_candidate_score": int(adjusted_candidate_score),
            "review_prior_multiplier": prior.multiplier,
            "review_prior_formula_version": REVIEW_PRIOR_FORMULA_VERSION,
            "review_prior": prior.as_explanation(),
            "score_semantics": (
                "heuristic ranking score adjusted by operator review prior; "
                "not outcome utility"
            ),
            "adjustment": {
                "kind": "operator_review_prior",
                "base_score_field": "base_candidate_score",
                "adjusted_score_field": "adjusted_candidate_score",
                "multiplier": prior.multiplier,
            },
        }
    )
    return features


def _apply_review_prior_to_surface_candidate(
    candidate: SurfaceComponentActionCandidate,
    review_priors: Mapping[tuple[str, str], ActionExperienceProposalReviewPrior],
) -> SurfaceComponentActionCandidate:
    prior = _review_prior_for_candidate(review_priors, candidate.capability_id, candidate.profile_id)
    if prior is None:
        return candidate
    base_score = int(candidate.candidate_score)
    adjusted_score = int(round(_apply_review_prior_to_score(base_score, prior)))
    return replace(
        candidate,
        candidate_score=adjusted_score,
        score_features=_score_features_after_review_prior(
            score_features=candidate.score_features,
            base_candidate_score=base_score,
            adjusted_candidate_score=adjusted_score,
            prior=prior,
        ),
    )

def _review_status(value: str) -> str:
    status = _required_text(value, "status")
    if status not in {"accepted", "rejected", "suppressed"}:
        raise ValueError("status must be accepted, rejected, or suppressed")
    return status


def _confidence(value: float) -> float:
    confidence = float(value)
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be between 0 and 1")
    return confidence
