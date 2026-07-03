from __future__ import annotations

from .surface_gds_models import (
    SurfaceComponent,
    SurfaceComponentActionCandidate,
    SurfaceComponentBridgeProfile,
    SurfaceComponentCoverageProfile,
    SurfaceComponentDrift,
    SurfaceComponentOutlierProfile,
    SurfaceComponentProfile,
)
from .surface_gds_signals import (
    _bridge_pressure_signal,
    _clamp,
    _component_action_candidate_signal_features,
    _component_action_candidate_signal,
    _component_attention_signal,
    _component_drift_signal,
    _coverage_signal,
    _exploration_pressure_signal,
    _outlier_signal,
    _structural_pressure_signal,
)


def _component_from_row(row: dict[str, object]) -> SurfaceComponent:
    return SurfaceComponent(
        component_id=int(row["component_id"]),
        node_count=int(row["node_count"]),
        avg_novelty_score=float(row["avg_novelty_score"]),
        max_novelty_score=int(row["max_novelty_score"]),
    )


def _component_action_candidate_from_row(row: dict[str, object]) -> SurfaceComponentActionCandidate:
    node_count = max(0, int(row["node_count"]))
    changed_node_count = max(0, int(row["changed_node_count"]))
    max_novelty_score = int(row["max_novelty_score"])
    sample_count = max(0, int(row["sample_count"]))
    avg_similarity = _clamp(float(row["avg_similarity"]))
    avg_information_gain_score = float(row["avg_information_gain_score"])
    human_positive_rate = _clamp(float(row["human_positive_rate"]))
    human_stop_rate = _clamp(float(row["human_stop_rate"]))
    utility_score = float(row["utility_score"])
    component_attention_score = _component_attention_signal(
        node_count=node_count,
        changed_node_count=changed_node_count,
        max_novelty_score=max_novelty_score,
    )
    candidate_score = _component_action_candidate_signal(
        component_attention_score=component_attention_score,
        sample_count=sample_count,
        avg_similarity=avg_similarity,
        utility_score=utility_score,
        human_stop_rate=human_stop_rate,
    )
    score_features = _component_action_candidate_signal_features(
        component_attention_score=component_attention_score,
        sample_count=sample_count,
        avg_similarity=avg_similarity,
        utility_score=utility_score,
        human_stop_rate=human_stop_rate,
    )
    return SurfaceComponentActionCandidate(
        component_id=int(row["component_id"]),
        node_count=node_count,
        changed_node_count=changed_node_count,
        max_novelty_score=max_novelty_score,
        capability_id=str(row["capability_id"]),
        profile_id=str(row["profile_id"]),
        sample_count=sample_count,
        avg_similarity=avg_similarity,
        avg_information_gain_score=avg_information_gain_score,
        human_positive_rate=human_positive_rate,
        human_stop_rate=human_stop_rate,
        utility_score=utility_score,
        component_attention_score=component_attention_score,
        candidate_score=candidate_score,
        ranker_kind=str(score_features["ranker_kind"]),
        calibration_status=str(score_features["calibration_status"]),
        score_formula_version=str(score_features["formula_version"]),
        score_features=score_features,
    )


def _component_coverage_from_row(row: dict[str, object]) -> SurfaceComponentCoverageProfile:
    node_count = max(0, int(row["node_count"]))
    changed_node_count = max(0, int(row["changed_node_count"]))
    action_outcome_count = max(0, int(row["action_outcome_count"]))
    positive_outcome_count = max(0, int(row["positive_outcome_count"]))
    stop_outcome_count = max(0, int(row["stop_outcome_count"]))
    avg_outcome_utility = float(row["avg_outcome_utility"])
    max_novelty_score = int(row["max_novelty_score"])
    novelty_density = changed_node_count / node_count if node_count > 0 else 0.0
    coverage_score = _coverage_signal(
        action_outcome_count=action_outcome_count,
        positive_outcome_count=positive_outcome_count,
        stop_outcome_count=stop_outcome_count,
        avg_outcome_utility=avg_outcome_utility,
    )
    exploration_priority_score = _exploration_pressure_signal(
        node_count=node_count,
        novelty_density=novelty_density,
        max_novelty_score=max_novelty_score,
        coverage_score=coverage_score,
    )
    return SurfaceComponentCoverageProfile(
        component_id=int(row["component_id"]),
        node_count=node_count,
        changed_node_count=changed_node_count,
        action_outcome_count=action_outcome_count,
        positive_outcome_count=positive_outcome_count,
        stop_outcome_count=stop_outcome_count,
        avg_outcome_utility=avg_outcome_utility,
        novelty_density=novelty_density,
        max_novelty_score=max_novelty_score,
        coverage_score=coverage_score,
        exploration_priority_score=exploration_priority_score,
    )


def _component_outlier_from_row(row: dict[str, object]) -> SurfaceComponentOutlierProfile:
    node_count = max(0, int(row["node_count"]))
    changed_node_count = max(0, int(row["changed_node_count"]))
    avg_similarity = _clamp(float(row["avg_similarity"]))
    max_similarity = _clamp(float(row["max_similarity"]))
    low_similarity_node_count = max(0, int(row["low_similarity_node_count"]))
    max_novelty_score = int(row["max_novelty_score"])
    novelty_density = changed_node_count / node_count if node_count > 0 else 0.0
    outlier_score = _outlier_signal(
        node_count=node_count,
        novelty_density=novelty_density,
        max_novelty_score=max_novelty_score,
        avg_similarity=avg_similarity,
        max_similarity=max_similarity,
        low_similarity_node_count=low_similarity_node_count,
    )
    return SurfaceComponentOutlierProfile(
        component_id=int(row["component_id"]),
        node_count=node_count,
        changed_node_count=changed_node_count,
        avg_similarity=avg_similarity,
        max_similarity=max_similarity,
        low_similarity_node_count=low_similarity_node_count,
        novelty_density=novelty_density,
        max_novelty_score=max_novelty_score,
        outlier_score=outlier_score,
    )


def _component_drift_from_row(row: dict[str, object]) -> SurfaceComponentDrift:
    current_node_count = max(0, int(row["current_node_count"]))
    previous_node_count = max(0, int(row["previous_node_count"]))
    shared_node_count = max(0, int(row["shared_node_count"]))
    introduced_node_count = max(0, int(row["introduced_node_count"]))
    removed_node_count = max(0, int(row["removed_node_count"]))
    jaccard_similarity = _clamp(float(row["jaccard_similarity"]))
    avg_novelty_score = float(row["avg_novelty_score"])
    max_novelty_score = int(row["max_novelty_score"])
    previous_component_raw = row.get("previous_component_id")
    previous_component_id = None if previous_component_raw is None else int(previous_component_raw)
    drift_score = _component_drift_signal(
        current_node_count=current_node_count,
        previous_node_count=previous_node_count,
        introduced_node_count=introduced_node_count,
        removed_node_count=removed_node_count,
        jaccard_similarity=jaccard_similarity,
        max_novelty_score=max_novelty_score,
    )
    return SurfaceComponentDrift(
        current_component_id=int(row["current_component_id"]),
        previous_component_id=previous_component_id,
        current_node_count=current_node_count,
        previous_node_count=previous_node_count,
        shared_node_count=shared_node_count,
        introduced_node_count=introduced_node_count,
        removed_node_count=removed_node_count,
        jaccard_similarity=jaccard_similarity,
        avg_novelty_score=avg_novelty_score,
        max_novelty_score=max_novelty_score,
        drift_score=drift_score,
    )


def _component_profile_from_row(row: dict[str, object]) -> SurfaceComponentProfile:
    node_count = max(0, int(row["node_count"]))
    changed_node_count = max(0, int(row["changed_node_count"]))
    avg_novelty_score = float(row["avg_novelty_score"])
    max_novelty_score = int(row["max_novelty_score"])
    avg_degree = float(row["avg_degree"])
    max_degree = float(row["max_degree"])
    novelty_density = changed_node_count / node_count if node_count > 0 else 0.0
    structural_pressure_score = _structural_pressure_signal(
        node_count=node_count,
        novelty_density=novelty_density,
        max_novelty_score=max_novelty_score,
        max_degree=max_degree,
    )
    raw_fingerprints = row.get("node_fingerprints") or ()
    node_fingerprints = tuple(str(item) for item in raw_fingerprints if item)
    return SurfaceComponentProfile(
        component_id=int(row["component_id"]),
        node_count=node_count,
        changed_node_count=changed_node_count,
        avg_novelty_score=avg_novelty_score,
        max_novelty_score=max_novelty_score,
        avg_degree=avg_degree,
        max_degree=max_degree,
        novelty_density=novelty_density,
        structural_pressure_score=structural_pressure_score,
        node_fingerprints=node_fingerprints,
    )


def _component_bridge_from_row(row: dict[str, object]) -> SurfaceComponentBridgeProfile:
    node_count = max(0, int(row["node_count"]))
    changed_node_count = max(0, int(row["changed_node_count"]))
    avg_betweenness = float(row["avg_betweenness"])
    max_betweenness = float(row["max_betweenness"])
    avg_degree = float(row["avg_degree"])
    max_degree = float(row["max_degree"])
    max_novelty_score = int(row["max_novelty_score"])
    novelty_density = changed_node_count / node_count if node_count > 0 else 0.0
    bridge_pressure_score = _bridge_pressure_signal(
        node_count=node_count,
        novelty_density=novelty_density,
        max_novelty_score=max_novelty_score,
        max_degree=max_degree,
        avg_betweenness=avg_betweenness,
        max_betweenness=max_betweenness,
    )
    return SurfaceComponentBridgeProfile(
        component_id=int(row["component_id"]),
        node_count=node_count,
        changed_node_count=changed_node_count,
        avg_betweenness=avg_betweenness,
        max_betweenness=max_betweenness,
        avg_degree=avg_degree,
        max_degree=max_degree,
        novelty_density=novelty_density,
        max_novelty_score=max_novelty_score,
        bridge_pressure_score=bridge_pressure_score,
    )
