from __future__ import annotations

import sys
from pathlib import Path

import pytest


def _symbols():
    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.action_outcome_gds import (
        ACTION_EXPERIENCE_PROBE_GDS_CYPHER,
        ACTION_OUTCOME_GDS_UTILITY_CYPHER,
        ActionOutcomeGdsUtilityReader,
    )

    return ACTION_OUTCOME_GDS_UTILITY_CYPHER, ACTION_EXPERIENCE_PROBE_GDS_CYPHER, ActionOutcomeGdsUtilityReader


class RecordingSession:
    def __init__(self):
        self.calls = []

    def run(self, query, parameters=None):
        self.calls.append((query, parameters or {}))
        return [
            {
                "capability_id": "web.http_probe",
                "profile_id": "passive-default",
                "sample_count": 3,
                "avg_similarity": 0.75,
                "avg_information_gain_score": 5.0,
                "human_positive_rate": 0.5,
                "human_stop_rate": 0.0,
                "utility_score": 5.625,
            }
        ]


def test_action_outcome_gds_query_uses_neo4j_algorithms_over_feature_graph() -> None:
    cypher, _, _ = _symbols()

    assert "gds.graph.project.cypher" in cypher
    assert "gds.nodeSimilarity.stream" in cypher
    assert "ActionOutcome" in cypher
    assert "OutcomeFeature" in cypher
    assert "HAS_OUTCOME_FEATURE" in cypher
    assert "MATCH (" in cypher
    assert "SELECT" not in cypher.upper()


def test_action_outcome_gds_reader_returns_ranked_candidates() -> None:
    _, _, Reader = _symbols()
    session = RecordingSession()

    candidates = Reader().rank_capability_profiles(
        session,
        program_id="00000000-0000-0000-0000-000000000001",
        seed_outcome_id="00000000-0000-0000-0000-000000000002",
        limit=5,
    )

    assert len(candidates) == 1
    assert candidates[0].capability_id == "web.http_probe"
    assert candidates[0].utility_score == 5.625
    query, parameters = session.calls[0]
    assert "gds.nodeSimilarity.stream" in query
    assert parameters["limit"] == 5


def test_action_experience_probe_query_scores_read_only_jaccard_without_transient_probe() -> None:
    _, cypher, _ = _symbols()

    assert "ActionExperienceProbe" not in cypher
    assert "MERGE" not in cypher
    assert "similar_outcome.capability_id = profile.capability_id" in cypher
    assert "capability_profile:" in cypher
    assert "DETACH DELETE" not in cypher
    assert "gds.graph.project.cypher" not in cypher
    assert "gds.nodeSimilarity.stream" not in cypher
    assert "intersection_size" in cypher
    assert "union_size" in cypher
    assert "OutcomeFeature" in cypher
    assert "CapabilityProfile" in cypher
    assert "SELECT" not in cypher.upper()


def test_action_experience_probe_reader_ranks_candidates_from_feature_keys() -> None:
    _, _, Reader = _symbols()
    session = RecordingSession()

    candidates = Reader().rank_capability_profiles_for_probe(
        session,
        program_id="00000000-0000-0000-0000-000000000001",
        probe_id="probe-1",
        feature_keys=[
            "node:katana",
            "event:web.crawl",
            "node:katana",
            "  observation_bucket:6-20  ",
        ],
        limit=7,
    )

    assert len(candidates) == 1
    assert candidates[0].profile_id == "passive-default"
    query, parameters = session.calls[0]
    assert "ActionExperienceProbe" not in query
    assert "MERGE" not in query
    assert "DETACH DELETE" not in query
    assert "gds.nodeSimilarity.stream" not in query
    assert parameters["limit"] == 7
    assert "probe_key" not in parameters
    assert "probe_id" not in parameters
    assert parameters["feature_keys"] == ["node:katana", "event:web.crawl", "observation_bucket:6-20"]
    assert parameters["candidate_profile_limit"] == 100


def test_action_experience_probe_rejects_empty_feature_keys() -> None:
    _, _, Reader = _symbols()

    with pytest.raises(ValueError, match="feature_keys"):
        Reader().rank_capability_profiles_for_probe(
            RecordingSession(),
            program_id="program",
            feature_keys=["", "  "],
        )



def test_action_experience_probe_reader_rejects_bad_candidate_profile_limit() -> None:
    _, _, Reader = _symbols()

    with pytest.raises(ValueError, match="candidate_profile_limit"):
        Reader().rank_capability_profiles_for_probe(
            RecordingSession(),
            program_id="program",
            feature_keys=["node:katana"],
            candidate_profile_limit=0,
        )


def test_action_outcome_gds_reader_rejects_unsafe_graph_names() -> None:
    _, _, Reader = _symbols()

    with pytest.raises(ValueError, match="unsafe GDS graph name"):
        Reader().rank_capability_profiles(
            RecordingSession(),
            program_id="program",
            seed_outcome_id="seed",
            graph_name="bad graph; DROP",
        )


def test_action_experience_probe_reader_rejects_unsafe_probe_ids() -> None:
    _, _, Reader = _symbols()

    with pytest.raises(ValueError, match="unsafe probe id"):
        Reader().rank_capability_profiles_for_probe(
            RecordingSession(),
            program_id="program",
            probe_id="bad probe; DETACH",
            feature_keys=["node:katana"],
        )
