from __future__ import annotations

import sys
from pathlib import Path
from uuid import UUID

from tests.infrastructure.surface_graph_math_support import RecordingSession, projector_symbols as _projector_symbols


def test_surface_map_producer_projects_snapshot_nodes_edges_and_deltas():
    Producer, *_ = _projector_symbols()
    program_id = UUID("00000000-0000-0000-0000-000000000001")
    batch = Producer().produce(
        [
            {
                "program_id": program_id,
                "snapshot_id": "snap-1",
                "snapshot_fingerprint": "s" * 64,
                "snapshot_algorithm_version": "surface-map-v1",
                "node_fingerprint": "n1",
                "node_type": "endpoint",
                "feature_fingerprint": "f1",
                "src_node_fingerprint": "n1",
                "dst_node_fingerprint": "n2",
                "edge_type": "HAS_ROUTE_SHAPE",
                "edge_fingerprint": "e1",
                "weight": 1.0,
                "delta_type": "node_introduced",
                "delta_subject_type": "endpoint",
                "delta_subject_fingerprint": "n1",
                "novelty_score": 55,
            }
        ]
    )

    assert batch is not None
    node_identities = {(fact.kind, fact.key) for fact in batch.facts if hasattr(fact, "kind")}
    edge_kinds = {fact.edge_kind for fact in batch.facts if hasattr(fact, "edge_kind")}
    assert ("SurfaceSnapshot", "snap-1") in node_identities
    assert ("SurfaceNode", "snap-1:n1") in node_identities
    assert ("SurfaceDelta", "snap-1:node_introduced:n1") in node_identities
    assert ("SurfaceFingerprint", "n1") in node_identities
    assert {
        "HAS_SURFACE_NODE",
        "SURFACE_EDGE",
        "HAS_SURFACE_DELTA",
        "HAS_SURFACE_FINGERPRINT",
    }.issubset(edge_kinds)
