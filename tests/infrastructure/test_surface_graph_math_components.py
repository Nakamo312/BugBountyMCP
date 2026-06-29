from __future__ import annotations

import sys
from pathlib import Path
from uuid import UUID

from tests.infrastructure.surface_graph_math_support import RecordingSession, projector_symbols as _projector_symbols


def test_surface_gds_reader_uses_wcc_over_surface_nodes():
    _, cypher, _, _, _, _, Reader, _, _, _, _ = _projector_symbols()
    session = RecordingSession()

    components = Reader().connected_components(
        session,
        program_id="00000000-0000-0000-0000-000000000001",
        snapshot_id="snap-1",
        limit=5,
    )

    assert "gds.graph.project.cypher" in cypher
    assert "gds.wcc.stream" in cypher
    assert "SurfaceNode" in cypher
    assert "SURFACE_EDGE" in cypher
    assert "SELECT" not in cypher.upper()
    assert components[0].component_id == 1
    assert components[0].max_novelty_score == 60
    query, parameters = session.calls[0]
    assert "gds.wcc.stream" in query
    assert parameters["limit"] == 5


def test_surface_gds_reader_uses_unique_runtime_graph_names_per_call():
    *_, Reader, _, _, _, _ = _projector_symbols()
    session = RecordingSession()

    Reader().connected_components(
        session,
        program_id="00000000-0000-0000-0000-000000000001",
        snapshot_id="snap-1",
    )
    Reader().connected_components(
        session,
        program_id="00000000-0000-0000-0000-000000000001",
        snapshot_id="snap-1",
    )

    first = session.calls[0][1]["graph_name"]
    second = session.calls[1][1]["graph_name"]
    assert first.startswith("surface_snapshot_wcc_")
    assert second.startswith("surface_snapshot_wcc_")
    assert first != second


def test_surface_component_profiles_use_degree_and_wcc():
    _, _, cypher, _, _, _, Reader, _, _, _, _ = _projector_symbols()
    session = RecordingSession()

    profiles = Reader().component_profiles(
        session,
        program_id="00000000-0000-0000-0000-000000000001",
        snapshot_id="snap-1",
        limit=1,
    )

    assert "gds.graph.project.cypher" in cypher
    assert "gds.wcc.stream" in cypher
    assert "gds.degree.stream" in cypher
    assert "gds.graph.drop" in cypher
    assert len(profiles) == 1
    assert profiles[0].component_id == 1
    assert profiles[0].node_count == 5
    assert profiles[0].changed_node_count == 2
    assert profiles[0].novelty_density == 0.4
    assert profiles[0].structural_pressure_score > 0
    query, parameters = session.calls[0]
    assert "gds.degree.stream" in query
    assert parameters["graph_name"].startswith("surface_snapshot_component_profile_")


def test_surface_component_bridges_use_betweenness_degree_and_wcc():
    _, _, _, bridge_cypher, _, _, Reader, bridge_score, _, _, _ = _projector_symbols()
    session = RecordingSession()

    bridges = Reader().component_bridges(
        session,
        program_id="00000000-0000-0000-0000-000000000001",
        snapshot_id="snap-1",
        limit=1,
    )

    assert "gds.graph.project.cypher" in bridge_cypher
    assert "gds.wcc.stream" in bridge_cypher
    assert "gds.degree.stream" in bridge_cypher
    assert "gds.betweenness.stream" in bridge_cypher
    assert "gds.graph.drop" in bridge_cypher
    assert len(bridges) == 1
    assert bridges[0].component_id == 3
    assert bridges[0].node_count == 7
    assert bridges[0].changed_node_count == 3
    assert bridges[0].novelty_density == 3 / 7
    assert bridges[0].max_betweenness == 18.0
    assert bridges[0].bridge_pressure_score > 0
    query, parameters = session.calls[0]
    assert "gds.betweenness.stream" in query
    assert parameters["graph_name"].startswith("surface_snapshot_component_bridges_")

    low = bridge_score(
        node_count=2,
        novelty_density=0.0,
        max_novelty_score=0,
        max_degree=1.0,
        avg_betweenness=0.0,
        max_betweenness=0.0,
    )
    high = bridge_score(
        node_count=8,
        novelty_density=0.4,
        max_novelty_score=70,
        max_degree=5.0,
        avg_betweenness=3.0,
        max_betweenness=20.0,
    )
    assert low < high


def test_surface_component_outliers_use_node_similarity_and_wcc():
    _, _, _, _, _, outlier_cypher, Reader, _, _, outlier_score, _ = _projector_symbols()
    session = RecordingSession()

    outliers = Reader().component_outliers(
        session,
        program_id="00000000-0000-0000-0000-000000000001",
        snapshot_id="snap-1",
        limit=1,
        similarity_cutoff=0.02,
        top_k=12,
    )

    assert "gds.graph.project.cypher" in outlier_cypher
    assert "gds.wcc.stream" in outlier_cypher
    assert "gds.nodeSimilarity.stream" in outlier_cypher
    assert "gds.graph.drop" in outlier_cypher
    assert len(outliers) == 1
    assert outliers[0].component_id == 9
    assert outliers[0].node_count == 5
    assert outliers[0].changed_node_count == 4
    assert outliers[0].novelty_density == 4 / 5
    assert outliers[0].avg_similarity == 0.08
    assert outliers[0].low_similarity_node_count == 5
    assert outliers[0].outlier_score > 0
    query, parameters = session.calls[0]
    assert "gds.nodeSimilarity.stream" in query
    assert parameters["graph_name"].startswith("surface_snapshot_component_outliers_")
    assert parameters["similarity_cutoff"] == 0.02
    assert parameters["top_k"] == 12

    familiar = outlier_score(
        node_count=8,
        novelty_density=0.0,
        max_novelty_score=0,
        avg_similarity=0.85,
        max_similarity=0.95,
        low_similarity_node_count=0,
    )
    strange = outlier_score(
        node_count=5,
        novelty_density=0.8,
        max_novelty_score=85,
        avg_similarity=0.08,
        max_similarity=0.12,
        low_similarity_node_count=5,
    )
    assert familiar < strange


def test_structural_pressure_prefers_novel_attached_components():
    *_, score = _projector_symbols()

    weak = score(
        node_count=2,
        novelty_density=0.0,
        max_novelty_score=0,
        max_degree=1.0,
    )
    strong = score(
        node_count=8,
        novelty_density=0.5,
        max_novelty_score=80,
        max_degree=5.0,
    )

    assert weak < strong
    assert 0 <= weak <= 100
    assert 0 <= strong <= 100
