from __future__ import annotations

import sys
from pathlib import Path

import pytest


def _symbols():
    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.action_experience_probe import (
        ACTION_EXPERIENCE_PROBE_FEATURES_CYPHER,
        ActionExperienceProbeFeatureBuilder,
        ActionExperienceProbeRanker,
    )

    return ACTION_EXPERIENCE_PROBE_FEATURES_CYPHER, ActionExperienceProbeFeatureBuilder, ActionExperienceProbeRanker


class CountingSession:
    def __init__(self):
        self.calls = []

    def run(self, query, parameters=None):
        self.calls.append((query, parameters or {}))
        if "RETURN host_count" in query:
            return [
                {
                    "host_count": 2,
                    "service_count": 4,
                    "endpoint_count": 18,
                    "parameter_count": 7,
                    "javascript_file_count": 3,
                    "outcome_count": 41,
                }
            ]
        return [
            {
                "capability_id": "web.crawl",
                "profile_id": "passive-default",
                "sample_count": 5,
                "avg_similarity": 0.64,
                "avg_information_gain_score": 9.0,
                "human_positive_rate": 0.2,
                "human_stop_rate": 0.0,
                "utility_score": 6.912,
            }
        ]


def test_action_experience_probe_features_are_built_from_neo4j_current_state() -> None:
    cypher, Builder, _ = _symbols()
    session = CountingSession()

    feature_set = Builder().build_from_graph(
        session,
        program_id="program-1",
        node_id="katana",
        event_name="web.crawl",
        target_count=11,
        base_feature_keys=["status:completed", "status:completed", "  "],
    )

    assert "MATCH (host:Host" in cypher
    assert "MATCH (endpoint:Endpoint" in cypher
    assert "MATCH (outcome:ActionOutcome" in cypher
    assert "SELECT" not in cypher.upper()
    assert feature_set.program_id == "program-1"
    assert feature_set.graph_counts["endpoint_count"] == 18
    assert feature_set.feature_keys == (
        "status:completed",
        "node:katana",
        "event:web.crawl",
        "target_count_bucket:6-20",
        "surface_hosts_bucket:2-5",
        "surface_services_bucket:2-5",
        "surface_endpoints_bucket:6-20",
        "javascript_reference_bucket:2-5",
        "observation_bucket:21-100",
    )
    query, parameters = session.calls[0]
    assert "ActionOutcome" in query
    assert parameters == {"program_id": "program-1"}


def test_action_experience_probe_ranker_uses_built_features_for_read_only_similarity() -> None:
    _, _, Ranker = _symbols()
    session = CountingSession()

    ranking = Ranker().rank_for_current_graph_state(
        session,
        program_id="program-1",
        node_id="katana",
        event_name="web.crawl",
        target_count=11,
        probe_id="probe-33",
        limit=3,
    )

    assert len(ranking.candidates) == 1
    assert ranking.candidates[0].capability_id == "web.crawl"
    assert ranking.feature_set.feature_keys[0] == "node:katana"
    query, gds_parameters = session.calls[1]
    assert "ActionExperienceProbe" not in query
    assert "MERGE" not in query
    assert "DETACH DELETE" not in query
    assert "probe_key" not in gds_parameters
    assert "probe_id" not in gds_parameters
    assert gds_parameters["limit"] == 3
    assert gds_parameters["feature_keys"] == list(ranking.feature_set.feature_keys)


def test_action_experience_probe_builder_rejects_negative_target_count() -> None:
    _, Builder, _ = _symbols()

    with pytest.raises(ValueError, match="target_count"):
        Builder().build_from_graph(CountingSession(), program_id="program-1", target_count=-1)
