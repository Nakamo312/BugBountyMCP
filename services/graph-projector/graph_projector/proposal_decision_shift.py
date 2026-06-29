from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping
from uuid import UUID

from .proposal_row_codec import _required_text


@dataclass(frozen=True)
class ActionExperienceDecisionShiftResult:
    proposal_run_id: UUID
    candidate_count: int
    previous_candidate_count: int
    entropy: float
    previous_entropy: float | None
    entropy_delta: float | None
    focus_gain: float | None
    top_k_overlap: float | None
    total_variation_distance: float | None
    rank_movement_score: float | None
    decision_shift_score: float
    decision_volatility_score: float | None = None
    metric_name: str = "decision_volatility"
    primary_score_field: str = "decision_volatility_score"
    deprecated_score_fields: tuple[str, ...] = ("decision_shift_score",)

def _decision_distribution_from_rows(rows: list[Mapping[str, Any]]) -> dict[str, object]:
    entries: list[dict[str, object]] = []
    total_score = 0.0
    for fallback_rank, row in enumerate(rows, start=1):
        capability_id = _required_text(row.get("capability_id"), "capability_id")
        profile_id = _required_text(row.get("profile_id"), "profile_id")
        score = max(0.0, float(row.get("utility_score") or 0.0))
        rank = int(row.get("rank") or fallback_rank)
        total_score += score
        entries.append(
            {
                "key": _candidate_distribution_key(capability_id, profile_id),
                "capability_id": capability_id,
                "profile_id": profile_id,
                "rank": rank,
                "utility_score": score,
                "weight": 0.0,
            }
        )
    if entries and total_score <= 0.0:
        weight = 1.0 / float(len(entries))
        for entry in entries:
            entry["weight"] = weight
    elif total_score > 0.0:
        for entry in entries:
            entry["weight"] = float(entry["utility_score"]) / total_score
    weights = [float(entry["weight"]) for entry in entries]
    entropy = _normalized_entropy(weights)
    return {
        "candidate_count": len(entries),
        "score_sum": total_score,
        "entropy": entropy,
        "top_keys": [str(entry["key"]) for entry in entries],
        "entries": entries,
    }


def _decision_shift_payload(
    *,
    current: dict[str, object],
    previous: dict[str, object] | None,
    previous_run_id: UUID | None,
    top_k: int,
) -> dict[str, object]:
    current_summary = _decision_distribution_summary(current)
    if previous is None:
        return {
            "decision_distribution": current_summary,
            "decision_shift": {
                "version": "decision-volatility.v1",
                "legacy_name": "decision_shift_score",
                "metric_name": "decision_volatility",
                "primary_score_field": "decision_volatility_score",
                "deprecated_score_fields": ("decision_shift_score",),
                "decision_shift_score_deprecated": True,
                "previous_proposal_run_id": None,
                "top_k": top_k,
                "previous_candidate_count": 0,
                "entropy_delta": None,
                "focus_gain": None,
                "top_k_overlap": None,
                "total_variation_distance": None,
                "rank_movement_score": None,
                "decision_shift_score": 0.0,
                "decision_volatility_score": 0.0,
                "utility_score": None,
            },
        }
    total_variation = _total_variation_distance(previous, current)
    overlap = _top_k_overlap(previous, current)
    rank_movement = _rank_movement_score(previous, current)
    entropy_delta = float(current["entropy"]) - float(previous["entropy"])
    focus_gain = -entropy_delta
    shift_score = 100.0 * (
        0.50 * total_variation
        + 0.25 * (1.0 - overlap)
        + 0.25 * rank_movement
    )
    return {
        "decision_distribution": current_summary,
        "decision_shift": {
            "version": "decision-volatility.v1",
            "legacy_name": "decision_shift_score",
            "metric_name": "decision_volatility",
            "primary_score_field": "decision_volatility_score",
            "deprecated_score_fields": ("decision_shift_score",),
            "decision_shift_score_deprecated": True,
            "previous_proposal_run_id": str(previous_run_id) if previous_run_id is not None else None,
            "top_k": top_k,
            "previous_candidate_count": int(previous["candidate_count"]),
            "entropy_delta": entropy_delta,
            "focus_gain": focus_gain,
            "top_k_overlap": overlap,
            "total_variation_distance": total_variation,
            "rank_movement_score": rank_movement,
            "decision_shift_score": max(0.0, min(100.0, shift_score)),
            "decision_volatility_score": max(0.0, min(100.0, shift_score)),
            "utility_score": None,
        },
    }


def _decision_distribution_summary(distribution: dict[str, object]) -> dict[str, object]:
    return {
        "version": "decision-distribution.v1",
        "candidate_count": int(distribution["candidate_count"]),
        "score_sum": float(distribution["score_sum"]),
        "entropy": float(distribution["entropy"]),
        "top_keys": list(distribution["top_keys"]),
    }


def _candidate_distribution_key(capability_id: str, profile_id: str) -> str:
    return f"{_required_text(capability_id, 'capability_id')}::{_required_text(profile_id, 'profile_id')}"


def _distribution_weights(distribution: dict[str, object]) -> dict[str, float]:
    weights: dict[str, float] = {}
    for entry in distribution.get("entries", []):
        if isinstance(entry, Mapping):
            weights[str(entry["key"])] = float(entry.get("weight") or 0.0)
    return weights


def _distribution_ranks(distribution: dict[str, object]) -> dict[str, int]:
    ranks: dict[str, int] = {}
    for fallback_rank, entry in enumerate(distribution.get("entries", []), start=1):
        if isinstance(entry, Mapping):
            ranks[str(entry["key"])] = int(entry.get("rank") or fallback_rank)
    return ranks


def _normalized_entropy(weights: list[float]) -> float:
    if len(weights) <= 1:
        return 0.0
    entropy = 0.0
    for weight in weights:
        if weight > 0:
            entropy -= weight * math.log(weight)
    return entropy / math.log(float(len(weights)))


def _total_variation_distance(previous: dict[str, object], current: dict[str, object]) -> float:
    previous_weights = _distribution_weights(previous)
    current_weights = _distribution_weights(current)
    keys = set(previous_weights) | set(current_weights)
    if not keys:
        return 0.0
    return 0.5 * sum(abs(current_weights.get(key, 0.0) - previous_weights.get(key, 0.0)) for key in keys)


def _top_k_overlap(previous: dict[str, object], current: dict[str, object]) -> float:
    previous_keys = set(_distribution_weights(previous))
    current_keys = set(_distribution_weights(current))
    union = previous_keys | current_keys
    if not union:
        return 1.0
    return float(len(previous_keys & current_keys)) / float(len(union))


def _rank_movement_score(previous: dict[str, object], current: dict[str, object]) -> float:
    previous_ranks = _distribution_ranks(previous)
    current_ranks = _distribution_ranks(current)
    shared = set(previous_ranks) & set(current_ranks)
    if not previous_ranks and not current_ranks:
        return 0.0
    if not shared:
        return 1.0
    max_rank = max(max(previous_ranks.values(), default=1), max(current_ranks.values(), default=1), 1)
    if max_rank <= 1:
        return 0.0
    movement = sum(abs(current_ranks[key] - previous_ranks[key]) / float(max_rank - 1) for key in shared)
    return max(0.0, min(1.0, movement / float(len(shared))))
