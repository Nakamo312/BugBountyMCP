from __future__ import annotations

from uuid import uuid4

from .proposal_keys import _proposal_key, _surface_component_proposal_key
from .proposal_review_priors import _review_prior_explanation


TERMINAL_PROPOSAL_STATUSES = ("accepting", "accepted", "accept_failed", "rejected", "suppressed")
_TERMINAL_STATUS_SQL = "action_experience_proposals.status IN (" + ", ".join(
    f"'{status}'" for status in TERMINAL_PROPOSAL_STATUSES
) + ")"


def _terminal_or_current(column: str) -> str:
    return f"CASE WHEN {_TERMINAL_STATUS_SQL} THEN action_experience_proposals.{column}"


_ACTION_EXPERIENCE_PROPOSAL_UPDATE_ASSIGNMENTS = ",\n".join(
    f"    {column} = {_terminal_or_current(column)} ELSE {'EXCLUDED.' + column if column != 'status' else "'pending'"} END"
    for column in (
        "proposal_run_id",
        "program_id",
        "campaign_id",
        "source_outcome_id",
        "source_action_id",
        "source_job_id",
        "source_run_id",
        "status",
        "rank",
        "capability_id",
        "profile_id",
        "utility_score",
        "sample_count",
        "avg_similarity",
        "avg_information_gain_score",
        "human_positive_rate",
        "human_stop_rate",
        "explanation",
        "produced_by",
        "updated_at",
    )
)


ACTION_EXPERIENCE_PROPOSAL_UPSERT_SQL = f"""
INSERT INTO action_experience_proposals (
    id,
    proposal_run_id,
    program_id,
    campaign_id,
    source_outcome_id,
    source_action_id,
    source_job_id,
    source_run_id,
    proposal_key,
    status,
    rank,
    capability_id,
    profile_id,
    utility_score,
    sample_count,
    avg_similarity,
    avg_information_gain_score,
    human_positive_rate,
    human_stop_rate,
    explanation,
    produced_by,
    created_at,
    updated_at
)
VALUES (
    %(id)s,
    %(proposal_run_id)s,
    %(program_id)s,
    %(campaign_id)s,
    %(source_outcome_id)s,
    %(source_action_id)s,
    %(source_job_id)s,
    %(source_run_id)s,
    %(proposal_key)s,
    %(status)s,
    %(rank)s,
    %(capability_id)s,
    %(profile_id)s,
    %(utility_score)s,
    %(sample_count)s,
    %(avg_similarity)s,
    %(avg_information_gain_score)s,
    %(human_positive_rate)s,
    %(human_stop_rate)s,
    %(explanation)s,
    %(produced_by)s,
    %(now)s,
    %(now)s
)
ON CONFLICT (proposal_key) DO UPDATE
SET {_ACTION_EXPERIENCE_PROPOSAL_UPDATE_ASSIGNMENTS};
""".strip()

def _candidate_value(candidate: object, name: str, fallback: object) -> object:
    value = getattr(candidate, name, None)
    return fallback if value is None else value


def _action_candidate_explanation(candidate: object) -> dict[str, object]:
    rank_score = _candidate_value(candidate, "rank_score", candidate.utility_score)
    return {
        "utility_score": candidate.utility_score,
        "base_utility_score": _candidate_value(candidate, "base_utility_score", candidate.utility_score),
        "utility_score_semantics": (
            "outcome-derived historical utility signal; "
            "not adjusted by operator review prior"
        ),
        "rank_score": rank_score,
        "adjusted_rank_score": _candidate_value(candidate, "adjusted_rank_score", rank_score),
        "review_prior_multiplier": _candidate_value(candidate, "review_prior_multiplier", 1.0),
        "review_prior_formula_version": getattr(candidate, "review_prior_formula_version", None),
        "rank_score_semantics": getattr(
            candidate,
            "rank_score_semantics",
            "outcome-derived utility rank score",
        ),
        "canonical_ordering_after_generation": "rank",
    }


def action_experience_proposal_values(
    *,
    proposal_run_id: object,
    source_values: dict[str, object],
    candidate: object,
    feature_builder_version: str,
    feature_count: int,
    rank: int,
    produced_by: str,
    now: object,
    proposal_source: str,
    review_prior: object | None = None,
) -> dict[str, object]:
    return {
        "id": uuid4(),
        "proposal_run_id": proposal_run_id,
        **source_values,
        "proposal_key": _proposal_key(
            source_values["source_outcome_id"],
            candidate.capability_id,
            candidate.profile_id,
            feature_builder_version,
        ),
        "status": "pending",
        "rank": rank,
        "capability_id": candidate.capability_id,
        "profile_id": candidate.profile_id,
        "utility_score": candidate.utility_score,
        "sample_count": candidate.sample_count,
        "avg_similarity": candidate.avg_similarity,
        "avg_information_gain_score": candidate.avg_information_gain_score,
        "human_positive_rate": candidate.human_positive_rate,
        "human_stop_rate": candidate.human_stop_rate,
        "explanation": {
            "source": proposal_source,
            "source_outcome_id": str(source_values["source_outcome_id"]),
            "feature_builder_version": feature_builder_version,
            "feature_count": feature_count,
            "rank": rank,
            "canonical_ordering_field": "rank",
            "candidate_basis": "similar historical state/action pairs ranked by generic OutcomeFeature Jaccard overlap",
            "action_candidate": _action_candidate_explanation(candidate),
            **_review_prior_explanation(review_prior),
        },
        "produced_by": produced_by,
        "now": now,
    }

def _surface_component_explanation(candidate: object) -> dict[str, object]:
    return {
        "node_count": candidate.node_count,
        "changed_node_count": candidate.changed_node_count,
        "max_novelty_score": candidate.max_novelty_score,
        "component_attention_score": candidate.component_attention_score,
    }


def _surface_candidate_explanation(candidate: object) -> dict[str, object]:
    score_features = getattr(candidate, "score_features", {})
    return {
        "component_similarity": candidate.avg_similarity,
        "utility_score": candidate.utility_score,
        "base_utility_score": candidate.utility_score,
        "utility_score_semantics": (
            "outcome-derived historical utility signal; "
            "not adjusted by operator review prior"
        ),
        "candidate_score": candidate.candidate_score,
        "rank_score": candidate.candidate_score,
        "candidate_score_semantics": (
            "uncalibrated heuristic ranking signal stored in the legacy "
            "candidate_score field; not outcome utility"
        ),
        "candidate_score_formula_version": getattr(candidate, "score_formula_version", None),
        "candidate_score_features": score_features,
        "base_candidate_score": score_features.get("base_candidate_score", candidate.candidate_score),
        "adjusted_candidate_score": score_features.get("adjusted_candidate_score", candidate.candidate_score),
        "review_prior_multiplier": score_features.get("review_prior_multiplier", 1.0),
        "review_prior_formula_version": score_features.get("review_prior_formula_version"),
        "score_features_stage": score_features.get("score_features_stage", "pre_review_prior"),
        "canonical_ordering_after_generation": "rank",
        "ranker_kind": getattr(candidate, "ranker_kind", None),
        "calibration_status": getattr(candidate, "calibration_status", None),
    }


def _surface_proposal_explanation(
    *,
    source_values: dict[str, object],
    snapshot_id: str,
    candidate: object,
    feature_builder_version: str,
    rank: int,
    proposal_source: str,
    review_prior: object | None,
) -> dict[str, object]:
    return {
        "source": proposal_source,
        "source_outcome_id": str(source_values["source_outcome_id"]),
        "feature_builder_version": feature_builder_version,
        "rank": rank,
        "canonical_ordering_field": "rank",
        "candidate_basis": (
            "changed surface component fingerprint set compared to historical "
            "outcome fingerprints by Jaccard overlap"
        ),
        "snapshot_id": snapshot_id,
        "component_id": candidate.component_id,
        "component": _surface_component_explanation(candidate),
        "surface_candidate": _surface_candidate_explanation(candidate),
        **_review_prior_explanation(review_prior),
    }


def surface_component_proposal_values(
    *,
    proposal_run_id: object,
    source_values: dict[str, object],
    snapshot_id: str,
    candidate: object,
    feature_builder_version: str,
    rank: int,
    produced_by: str,
    now: object,
    proposal_source: str,
    review_prior: object | None = None,
) -> dict[str, object]:
    return {
        "id": uuid4(),
        "proposal_run_id": proposal_run_id,
        **source_values,
        "proposal_key": _surface_component_proposal_key(
            source_values["source_outcome_id"],
            snapshot_id,
            candidate.component_id,
            candidate.capability_id,
            candidate.profile_id,
            feature_builder_version,
        ),
        "status": "pending",
        "rank": rank,
        "capability_id": candidate.capability_id,
        "profile_id": candidate.profile_id,
        "utility_score": float(candidate.utility_score),
        "sample_count": candidate.sample_count,
        "avg_similarity": candidate.avg_similarity,
        "avg_information_gain_score": candidate.avg_information_gain_score,
        "human_positive_rate": candidate.human_positive_rate,
        "human_stop_rate": candidate.human_stop_rate,
        "explanation": _surface_proposal_explanation(
            source_values=source_values,
            snapshot_id=snapshot_id,
            candidate=candidate,
            feature_builder_version=feature_builder_version,
            rank=rank,
            proposal_source=proposal_source,
            review_prior=review_prior,
        ),
        "produced_by": produced_by,
        "now": now,
    }
