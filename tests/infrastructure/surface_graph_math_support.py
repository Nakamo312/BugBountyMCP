from __future__ import annotations

import sys
from pathlib import Path
from uuid import UUID


def projector_symbols():
    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.producers.surface_map import SurfaceMapGraphFactProducer
    from graph_projector.surface_gds import (
        SURFACE_COMPONENT_BRIDGE_CYPHER,
        SURFACE_COMPONENT_DRIFT_CYPHER,
        SURFACE_COMPONENT_COVERAGE_CYPHER,
        SURFACE_COMPONENT_ACTION_CANDIDATE_CYPHER,
        SURFACE_COMPONENT_OUTLIER_CYPHER,
        SURFACE_COMPONENT_PROFILE_CYPHER,
        SURFACE_WCC_CYPHER,
        SurfaceGraphMathReader,
    )
    from graph_projector.surface_gds_scores import (
        _bridge_pressure_score,
        _component_drift_score,
        _component_action_candidate_score,
        _coverage_score,
        _exploration_priority_score,
        _outlier_score,
        _structural_pressure_score,
    )

    return (
        SurfaceMapGraphFactProducer,
        SURFACE_WCC_CYPHER,
        SURFACE_COMPONENT_PROFILE_CYPHER,
        SURFACE_COMPONENT_BRIDGE_CYPHER,
        SURFACE_COMPONENT_DRIFT_CYPHER,
        SURFACE_COMPONENT_OUTLIER_CYPHER,
        SurfaceGraphMathReader,
        _bridge_pressure_score,
        _component_drift_score,
        _outlier_score,
        _structural_pressure_score,
    )


class RecordingSession:
    def __init__(self):
        self.calls = []

    def run(self, query, parameters=None):
        self.calls.append((query, parameters or {}))
        if "current_graph_name" in query and "previous_graph_name" in query:
            return [
                {
                    "current_component_id": 2,
                    "previous_component_id": 4,
                    "current_node_count": 6,
                    "previous_node_count": 5,
                    "shared_node_count": 2,
                    "introduced_node_count": 4,
                    "removed_node_count": 3,
                    "jaccard_similarity": 0.22,
                    "avg_novelty_score": 25.0,
                    "max_novelty_score": 90,
                },
                {
                    "current_component_id": 1,
                    "previous_component_id": 1,
                    "current_node_count": 4,
                    "previous_node_count": 4,
                    "shared_node_count": 4,
                    "introduced_node_count": 0,
                    "removed_node_count": 0,
                    "jaccard_similarity": 1.0,
                    "avg_novelty_score": 0.0,
                    "max_novelty_score": 0,
                },
            ]
        if "component_fingerprints" in query:
            return [
                {
                    "component_id": 21,
                    "node_count": 7,
                    "changed_node_count": 5,
                    "max_novelty_score": 88,
                    "capability_id": "katana",
                    "profile_id": "safe-crawl",
                    "sample_count": 6,
                    "avg_similarity": 0.42,
                    "avg_information_gain_score": 8.0,
                    "human_positive_rate": 0.5,
                    "human_stop_rate": 0.0,
                    "utility_score": 2.75,
                },
                {
                    "component_id": 22,
                    "node_count": 4,
                    "changed_node_count": 1,
                    "max_novelty_score": 20,
                    "capability_id": "httpx",
                    "profile_id": "safe-web-probe",
                    "sample_count": 2,
                    "avg_similarity": 0.18,
                    "avg_information_gain_score": 2.0,
                    "human_positive_rate": 0.0,
                    "human_stop_rate": 0.5,
                    "utility_score": 0.15,
                },
            ]
        if "AFTER_SURFACE_SNAPSHOT" in query:
            return [
                {
                    "component_id": 11,
                    "node_count": 6,
                    "changed_node_count": 5,
                    "action_outcome_count": 0,
                    "positive_outcome_count": 0,
                    "stop_outcome_count": 0,
                    "avg_outcome_utility": 0.0,
                    "max_novelty_score": 90,
                },
                {
                    "component_id": 12,
                    "node_count": 8,
                    "changed_node_count": 2,
                    "action_outcome_count": 4,
                    "positive_outcome_count": 2,
                    "stop_outcome_count": 0,
                    "avg_outcome_utility": 6.5,
                    "max_novelty_score": 30,
                },
            ]
        if "gds.nodeSimilarity.stream" in query:
            return [
                {
                    "component_id": 9,
                    "node_count": 5,
                    "changed_node_count": 4,
                    "avg_similarity": 0.08,
                    "max_similarity": 0.12,
                    "low_similarity_node_count": 5,
                    "max_novelty_score": 85,
                },
                {
                    "component_id": 10,
                    "node_count": 6,
                    "changed_node_count": 0,
                    "avg_similarity": 0.78,
                    "max_similarity": 0.91,
                    "low_similarity_node_count": 0,
                    "max_novelty_score": 0,
                },
            ]
        if "gds.betweenness.stream" in query:
            return [
                {
                    "component_id": 3,
                    "node_count": 7,
                    "changed_node_count": 3,
                    "avg_betweenness": 2.5,
                    "max_betweenness": 18.0,
                    "avg_degree": 2.1,
                    "max_degree": 5.0,
                    "max_novelty_score": 70,
                },
                {
                    "component_id": 4,
                    "node_count": 3,
                    "changed_node_count": 0,
                    "avg_betweenness": 0.0,
                    "max_betweenness": 0.0,
                    "avg_degree": 1.0,
                    "max_degree": 1.0,
                    "max_novelty_score": 0,
                },
            ]
        if "gds.degree.stream" in query:
            return [
                {
                    "component_id": 1,
                    "node_count": 5,
                    "changed_node_count": 2,
                    "avg_novelty_score": 18.0,
                    "max_novelty_score": 80,
                    "avg_degree": 1.8,
                    "max_degree": 4.0,
                },
                {
                    "component_id": 2,
                    "node_count": 2,
                    "changed_node_count": 0,
                    "avg_novelty_score": 0.0,
                    "max_novelty_score": 0,
                    "avg_degree": 1.0,
                    "max_degree": 1.0,
                },
            ]
        return [
            {
                "component_id": 1,
                "node_count": 3,
                "avg_novelty_score": 42.5,
                "max_novelty_score": 60,
            }
        ]