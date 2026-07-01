from __future__ import annotations

import sys
from pathlib import Path
from uuid import UUID

from tests.infrastructure.surface_graph_math_support import RecordingSession, projector_symbols as _projector_symbols


def test_surface_component_coverage_joins_components_to_action_outcomes():
    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.surface_gds import SURFACE_COMPONENT_COVERAGE_CYPHER, SurfaceGraphMathReader
    from graph_projector.surface_gds_signals import _coverage_signal, _exploration_pressure_signal

    coverage_cypher = SURFACE_COMPONENT_COVERAGE_CYPHER
    Reader = SurfaceGraphMathReader
    coverage_score = _coverage_signal
    exploration_priority_score = _exploration_pressure_signal
    session = RecordingSession()

    coverage = Reader().component_coverage(
        session,
        program_id="00000000-0000-0000-0000-000000000001",
        snapshot_id="snap-1",
        limit=1,
    )

    assert "gds.graph.project.cypher" in coverage_cypher
    assert "gds.wcc.stream" in coverage_cypher
    assert "AFTER_SURFACE_SNAPSHOT" in coverage_cypher
    assert "ActionOutcome" in coverage_cypher
    assert "gds.graph.drop" in coverage_cypher
    assert len(coverage) == 1
    assert coverage[0].component_id == 11
    assert coverage[0].node_count == 6
    assert coverage[0].changed_node_count == 5
    assert coverage[0].action_outcome_count == 0
    assert coverage[0].novelty_density == 5 / 6
    assert coverage[0].coverage_score == 0
    assert coverage[0].exploration_priority_score > 0
    query, parameters = session.calls[0]
    assert "AFTER_SURFACE_SNAPSHOT" in query
    assert parameters["graph_name"].startswith("surface_snapshot_component_coverage_")

    uncovered_priority = exploration_priority_score(
        node_count=6,
        novelty_density=0.8,
        max_novelty_score=90,
        coverage_score=0,
    )
    covered_priority = exploration_priority_score(
        node_count=6,
        novelty_density=0.8,
        max_novelty_score=90,
        coverage_score=85,
    )
    assert uncovered_priority > covered_priority
    assert coverage_score(
        action_outcome_count=4,
        positive_outcome_count=2,
        stop_outcome_count=0,
        avg_outcome_utility=6.5,
    ) > 0


def test_surface_component_action_candidates_compare_component_fingerprints_to_outcomes_without_probe_writes():
    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.surface_gds import SURFACE_COMPONENT_ACTION_CANDIDATE_CYPHER, SurfaceGraphMathReader
    from graph_projector.surface_gds_signals import _component_action_candidate_signal

    session = RecordingSession()

    candidates = SurfaceGraphMathReader().component_action_candidates(
        session,
        program_id="00000000-0000-0000-0000-000000000001",
        snapshot_id="snap-1",
        limit=1,
        component_limit=3,
        similarity_cutoff=0.03,
        probe_id="probe-1",
    )

    assert "gds.graph.project.cypher" in SURFACE_COMPONENT_ACTION_CANDIDATE_CYPHER
    assert "gds.wcc.stream" in SURFACE_COMPONENT_ACTION_CANDIDATE_CYPHER
    assert "gds.nodeSimilarity.stream" not in SURFACE_COMPONENT_ACTION_CANDIDATE_CYPHER
    assert "SurfaceComponentProbe" not in SURFACE_COMPONENT_ACTION_CANDIDATE_CYPHER
    assert "SurfaceFingerprint" in SURFACE_COMPONENT_ACTION_CANDIDATE_CYPHER
    assert "AFTER_SURFACE_SNAPSHOT" in SURFACE_COMPONENT_ACTION_CANDIDATE_CYPHER
    assert "DETACH DELETE" not in SURFACE_COMPONENT_ACTION_CANDIDATE_CYPHER
    assert "intersection_size" in SURFACE_COMPONENT_ACTION_CANDIDATE_CYPHER
    assert "union_size" in SURFACE_COMPONENT_ACTION_CANDIDATE_CYPHER
    assert len(candidates) == 1
    assert candidates[0].component_id == 21
    assert candidates[0].capability_id == "katana"
    assert candidates[0].profile_id == "safe-crawl"
    assert candidates[0].component_attention_score > 0
    assert candidates[0].candidate_score > 0
    query, parameters = session.calls[0]
    assert "SurfaceComponentProbe" not in query
    assert "MERGE" not in query
    assert "DETACH DELETE" not in query
    assert parameters["wcc_graph_name"].startswith("surface_component_candidate_wcc_")
    assert parameters["component_limit"] == 3
    assert parameters["similarity_cutoff"] == 0.03
    assert "probe_id" not in parameters

    weak = _component_action_candidate_signal(
        component_attention_score=15,
        sample_count=1,
        avg_similarity=0.05,
        utility_score=0.1,
        human_stop_rate=0.7,
    )
    strong = _component_action_candidate_signal(
        component_attention_score=80,
        sample_count=10,
        avg_similarity=0.5,
        utility_score=5.0,
        human_stop_rate=0.0,
    )
    assert weak < strong
