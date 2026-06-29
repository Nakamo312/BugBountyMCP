from __future__ import annotations

import math
from typing import Any


SURFACE_GDS_SCORE_FORMULA_VERSION = "surface-gds-heuristic.v1"
SURFACE_GDS_RANKER_KIND = "heuristic"
SURFACE_GDS_CALIBRATION_STATUS = "uncalibrated"


def _component_attention_score(
    *,
    node_count: int,
    changed_node_count: int,
    max_novelty_score: int,
) -> int:
    density = _clamp(changed_node_count / max(1, node_count))
    novelty = _clamp(max_novelty_score / 100.0)
    size = _clamp(math.log1p(max(node_count, 0)) / math.log1p(50))
    score = 100.0 * (0.45 * novelty + 0.35 * density + 0.20 * size)
    return max(0, min(100, int(round(score))))


def _component_action_candidate_score(
    *,
    component_attention_score: int,
    sample_count: int,
    avg_similarity: float,
    utility_score: float,
    human_stop_rate: float,
) -> int:
    attention = _clamp(component_attention_score / 100.0)
    confidence = _clamp(sample_count / (sample_count + 5.0))
    similarity = _clamp(avg_similarity)
    utility = _clamp(math.log1p(max(0.0, utility_score)) / math.log1p(20.0))
    stop_penalty = 1.0 - _clamp(human_stop_rate)
    score = 100.0 * stop_penalty * (
        0.45 * utility + 0.25 * similarity + 0.20 * confidence + 0.10 * attention
    )
    return max(0, min(100, int(round(score))))


def _coverage_score(
    *,
    action_outcome_count: int,
    positive_outcome_count: int,
    stop_outcome_count: int,
    avg_outcome_utility: float,
) -> int:
    count = max(0, int(action_outcome_count))
    if count == 0:
        return 0
    confidence = _clamp(count / (count + 3.0))
    positive_rate = _clamp(positive_outcome_count / count)
    stop_rate = _clamp(stop_outcome_count / count)
    utility = _clamp(math.log1p(max(0.0, avg_outcome_utility)) / math.log1p(20.0))
    score = 100.0 * (
        0.45 * confidence
        + 0.25 * positive_rate
        + 0.20 * utility
        + 0.10 * (1.0 - stop_rate)
    )
    return max(0, min(100, int(round(score))))


def _exploration_priority_score(
    *,
    node_count: int,
    novelty_density: float,
    max_novelty_score: int,
    coverage_score: int,
) -> int:
    uncovered = 1.0 - _clamp(coverage_score / 100.0)
    novelty = _clamp(max_novelty_score / 100.0)
    density = _clamp(novelty_density)
    size = _clamp(math.log1p(max(node_count, 0)) / math.log1p(50))
    pressure = 0.45 * novelty + 0.35 * density + 0.20 * size
    score = 100.0 * uncovered * pressure
    return max(0, min(100, int(round(score))))


def _component_drift_score(
    *,
    current_node_count: int,
    previous_node_count: int,
    introduced_node_count: int,
    removed_node_count: int,
    jaccard_similarity: float,
    max_novelty_score: int,
) -> int:
    current_size = max(0, int(current_node_count))
    previous_size = max(0, int(previous_node_count))
    union_size = max(1, current_size + previous_size)
    overlap_shift = 1.0 - _clamp(jaccard_similarity)
    introduced_ratio = _clamp(introduced_node_count / max(1, current_size))
    removed_ratio = _clamp(removed_node_count / max(1, previous_size))
    size_delta = _clamp(abs(current_size - previous_size) / union_size)
    novelty = _clamp(max_novelty_score / 100.0)
    score = 100.0 * (
        0.40 * overlap_shift
        + 0.25 * introduced_ratio
        + 0.15 * removed_ratio
        + 0.15 * novelty
        + 0.05 * size_delta
    )
    return max(0, min(100, int(round(score))))


def _outlier_score(
    *,
    node_count: int,
    novelty_density: float,
    max_novelty_score: int,
    avg_similarity: float,
    max_similarity: float,
    low_similarity_node_count: int,
) -> int:
    novelty = _clamp(max_novelty_score / 100.0)
    density = _clamp(novelty_density)
    avg_dissimilarity = 1.0 - _clamp(avg_similarity)
    max_dissimilarity = 1.0 - _clamp(max_similarity)
    low_similarity_density = _clamp(low_similarity_node_count / max(1, node_count))
    size = _clamp(math.log1p(max(node_count, 0)) / math.log1p(50))
    score = 100.0 * (
        0.30 * avg_dissimilarity
        + 0.20 * max_dissimilarity
        + 0.20 * low_similarity_density
        + 0.15 * novelty
        + 0.10 * density
        + 0.05 * size
    )
    return max(0, min(100, int(round(score))))


def _bridge_pressure_score(
    *,
    node_count: int,
    novelty_density: float,
    max_novelty_score: int,
    max_degree: float,
    avg_betweenness: float,
    max_betweenness: float,
) -> int:
    novelty = _clamp(max_novelty_score / 100.0)
    density = _clamp(novelty_density)
    degree = _clamp(max_degree / 10.0)
    # Betweenness can be unbounded for larger graphs, so use concave scaling.
    # The score should react to bridge-like nodes without making graph size a
    # direct reward.
    max_bridge = _clamp(math.log1p(max(0.0, max_betweenness)) / math.log1p(100.0))
    avg_bridge = _clamp(math.log1p(max(0.0, avg_betweenness)) / math.log1p(100.0))
    size = _clamp(math.log1p(max(node_count, 0)) / math.log1p(50))
    score = 100.0 * (
        0.40 * max_bridge
        + 0.15 * avg_bridge
        + 0.15 * degree
        + 0.15 * novelty
        + 0.10 * density
        + 0.05 * size
    )
    return max(0, min(100, int(round(score))))


def _structural_pressure_score(
    *,
    node_count: int,
    novelty_density: float,
    max_novelty_score: int,
    max_degree: float,
) -> int:
    novelty = _clamp(max_novelty_score / 100.0)
    density = _clamp(novelty_density)
    degree = _clamp(max_degree / 10.0)
    size = _clamp(math.log1p(max(node_count, 0)) / math.log1p(50))
    score = 100.0 * (0.45 * novelty + 0.25 * density + 0.20 * degree + 0.10 * size)
    return max(0, min(100, int(round(score))))


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _component_action_candidate_features(
    *,
    component_attention_score: int,
    sample_count: int,
    avg_similarity: float,
    utility_score: float,
    human_stop_rate: float,
) -> dict[str, Any]:
    """Return raw and normalized inputs used by the candidate score.

    Scores remain heuristic. Persisting this payload next to the score keeps
    operators from treating the weighted sum as ground truth.
    """
    attention = _clamp(component_attention_score / 100.0)
    confidence = _clamp(sample_count / (sample_count + 5.0))
    similarity = _clamp(avg_similarity)
    utility = _clamp(math.log1p(max(0.0, utility_score)) / math.log1p(20.0))
    stop_penalty = 1.0 - _clamp(human_stop_rate)
    return {
        "formula_version": SURFACE_GDS_SCORE_FORMULA_VERSION,
        "ranker_kind": SURFACE_GDS_RANKER_KIND,
        "calibration_status": SURFACE_GDS_CALIBRATION_STATUS,
        "score_name": "candidate_score",
        "score_semantics": "legacy heuristic ranking score",
        "raw": {
            "component_attention_score": component_attention_score,
            "sample_count": sample_count,
            "avg_similarity": avg_similarity,
            "utility_score": utility_score,
            "human_stop_rate": human_stop_rate,
        },
        "normalized": {
            "attention": attention,
            "confidence": confidence,
            "similarity": similarity,
            "utility": utility,
            "stop_penalty": stop_penalty,
        },
        "weights": {
            "utility": 0.45,
            "similarity": 0.25,
            "confidence": 0.20,
            "attention": 0.10,
        },
        "explanation": (
            "heuristic weighted sum",
            "not calibrated from outcome feedback",
            "candidate_score is advisory, not learned utility",
            "use raw features for audit and future learned ranking",
        ),
    }
