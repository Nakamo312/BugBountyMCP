from __future__ import annotations

import sys
from pathlib import Path
from uuid import UUID

from tests.infrastructure.surface_graph_math_support import RecordingSession, projector_symbols as _projector_symbols


def test_surface_component_drift_compares_wcc_partitions_across_snapshots():
    _, _, _, _, drift_cypher, _, Reader, _, drift_score, _, _ = _projector_symbols()
    session = RecordingSession()

    drift = Reader().component_drift(
        session,
        program_id="00000000-0000-0000-0000-000000000001",
        previous_snapshot_id="snap-1",
        current_snapshot_id="snap-2",
        limit=1,
    )

    assert "gds.graph.project.cypher" in drift_cypher
    assert drift_cypher.count("gds.wcc.stream") == 2
    assert "jaccard_similarity" in drift_cypher
    assert "gds.graph.drop" in drift_cypher
    assert len(drift) == 1
    assert drift[0].current_component_id == 2
    assert drift[0].previous_component_id == 4
    assert drift[0].introduced_node_count == 4
    assert drift[0].removed_node_count == 3
    assert drift[0].jaccard_similarity == 0.22
    assert drift[0].drift_score > 0
    query, parameters = session.calls[0]
    assert "current_graph_name" in query
    assert parameters["previous_graph_name"].startswith("surface_snapshot_drift_previous_")
    assert parameters["current_graph_name"].startswith("surface_snapshot_drift_current_")
    assert parameters["previous_graph_name"] != parameters["current_graph_name"]

    stable = drift_score(
        current_node_count=5,
        previous_node_count=5,
        introduced_node_count=0,
        removed_node_count=0,
        jaccard_similarity=1.0,
        max_novelty_score=0,
    )
    shifted = drift_score(
        current_node_count=6,
        previous_node_count=5,
        introduced_node_count=4,
        removed_node_count=3,
        jaccard_similarity=0.2,
        max_novelty_score=90,
    )
    assert stable < shifted
