import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SURFACE_ROOT = ROOT / "services" / "surface-engine"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(SURFACE_ROOT))

from surface_engine.nodes import (  # noqa: E402
    build_snapshot_draft,
    build_surface_nodes_from_observation,
    build_surface_nodes_from_observations,
)

PROGRAM_ID = "00000000-0000-0000-0000-000000000001"


def _row(**overrides):
    row = {
        "id": "11111111-1111-1111-1111-111111111111",
        "program_id": PROGRAM_ID,
        "method": "POST",
        "url": "https://alice:secret@example.com/api/users/123?token=raw-token#frag",
        "scheme": "https",
        "host": "example.com",
        "port": 443,
        "status_code": 200,
        "content_type": "application/json; charset=utf-8",
        "body_sha256": "a" * 64,
        "body_size_bytes": 512,
        "body_preview": '{"email":"alex@example.com"}',
        "source_tool": "unit-test",
        "observed_at": "2026-06-10T00:00:00+00:00",
        "headers": [
            {"name": "Content-Type", "value": "application/json", "ordinal": 0},
            {"name": "Set-Cookie", "value": "session=secret", "ordinal": 1},
        ],
        "metadata": {
            "safe_features": {"json_keys": ["id", "email"]},
            "request": {
                "content_type": "application/x-www-form-urlencoded",
                "body_field_value_types": {"login": "string", "password": "string"},
            },
        },
    }
    row.update(overrides)
    return row


def test_surface_node_builder_creates_endpoint_route_and_response_shape_nodes():
    nodes = build_surface_nodes_from_observation(_row())

    assert {node.node_type for node in nodes} == {"endpoint", "route_template", "response_shape"}
    endpoint = next(node for node in nodes if node.node_type == "endpoint")
    route = next(node for node in nodes if node.node_type == "route_template")
    response = next(node for node in nodes if node.node_type == "response_shape")

    assert endpoint.ref_type == "http_observation"
    assert endpoint.host == "example.com"
    assert endpoint.route_template == "/api/users/{id}"
    assert route.ref_type == "route_template"
    assert response.ref_type == "response_shape"
    assert endpoint.safe_for_search is True


def test_surface_node_builder_does_not_leak_raw_values_header_values_or_body_preview():
    nodes = build_surface_nodes_from_observation(_row())
    payload = json.dumps([node.features_json for node in nodes], sort_keys=True)

    forbidden = [
        "alice",
        "secret@example.com",
        "raw-token",
        "frag",
        "session=secret",
        "alex@example.com",
    ]
    for value in forbidden:
        assert value not in payload

    assert "password" in payload
    assert "body_field:password:string" in payload
    assert "Set-Cookie" in payload or "set-cookie" in payload


def test_surface_node_builder_dedupes_same_shape_and_counts_observations():
    rows = [
        _row(id="11111111-1111-1111-1111-111111111111", url="https://example.com/api/users/123"),
        _row(id="22222222-2222-2222-2222-222222222222", url="https://example.com/api/users/456"),
    ]

    nodes = build_surface_nodes_from_observations(rows)
    endpoint_nodes = [node for node in nodes if node.node_type == "endpoint"]
    route_nodes = [node for node in nodes if node.node_type == "route_template"]

    assert len(endpoint_nodes) == 1
    assert len(route_nodes) == 1
    assert endpoint_nodes[0].features_json["surface_node"]["observation_count"] == 2
    assert set(endpoint_nodes[0].features_json["surface_node"]["exemplar_ref_ids"]) == {
        "11111111-1111-1111-1111-111111111111",
        "22222222-2222-2222-2222-222222222222",
    }


def test_snapshot_draft_is_deterministic_and_summarizes_node_types():
    rows = [_row(id="11111111-1111-1111-1111-111111111111")]
    nodes = build_surface_nodes_from_observations(rows)
    first = build_snapshot_draft(program_id=PROGRAM_ID, nodes=nodes, source_rows=rows)
    second = build_snapshot_draft(program_id=PROGRAM_ID, nodes=nodes, source_rows=rows)

    assert first.snapshot_fingerprint == second.snapshot_fingerprint
    assert first.algorithm == "surface-map"
    assert first.stats_json["observations_read"] == 1
    assert first.stats_json["nodes_deduped"] == 3
    assert first.stats_json["node_types"] == {
        "endpoint": 1,
        "response_shape": 1,
        "route_template": 1,
    }

from surface_engine.deltas import build_surface_deltas  # noqa: E402
from surface_engine.edges import build_surface_edges_from_nodes  # noqa: E402


def test_surface_edge_builder_connects_endpoint_shapes_without_domain_labels():
    nodes = build_surface_nodes_from_observations([_row()])
    edges = build_surface_edges_from_nodes(nodes)

    assert {edge.edge_type for edge in edges} == {"HAS_ROUTE_SHAPE", "HAS_RESPONSE_SHAPE"}
    assert all(edge.weight == 1.0 for edge in edges)
    payload = json.dumps([edge.evidence_json for edge in edges], sort_keys=True)
    assert "admin" not in payload.lower()
    assert "swagger" not in payload.lower()


def test_surface_delta_builder_scores_structural_introductions_not_counts():
    first_rows = [_row(id="11111111-1111-1111-1111-111111111111", url="https://example.com/api/users/123")]
    second_rows = [
        *first_rows,
        _row(id="22222222-2222-2222-2222-222222222222", url="https://example.com/api/orders/456"),
    ]
    first_nodes = build_surface_nodes_from_observations(first_rows)
    second_nodes = build_surface_nodes_from_observations(second_rows)
    first_edges = build_surface_edges_from_nodes(first_nodes)
    second_edges = build_surface_edges_from_nodes(second_nodes)

    deltas = build_surface_deltas(
        program_id=PROGRAM_ID,
        from_snapshot_id="snap-before",
        to_snapshot_id="snap-after",
        previous_nodes=[
            {"node_fingerprint": node.node_fingerprint, "feature_fingerprint": node.feature_fingerprint}
            for node in first_nodes
        ],
        previous_edges=[{"edge_fingerprint": edge.edge_fingerprint} for edge in first_edges],
        current_nodes=second_nodes,
        current_edges=second_edges,
    )

    assert any(delta.delta_type == "node_introduced" for delta in deltas)
    assert any(delta.delta_type == "edge_introduced" for delta in deltas)
    assert all(0 <= delta.novelty_score <= 100 for delta in deltas)
    assert all("score_basis" in delta.details_json for delta in deltas)


def test_surface_node_builder_is_split_into_package_modules():
    nodes_root = ROOT / "services/surface-engine/surface_engine/nodes"
    assert nodes_root.is_dir()
    assert not (ROOT / "services/surface-engine/surface_engine/nodes.py").exists()

    for module_name in ["models.py", "metadata.py", "drafts.py", "dedupe.py", "observation.py", "snapshot.py"]:
        assert (nodes_root / module_name).exists()

    observation_source = (nodes_root / "observation.py").read_text()
    assert "canonicalize_observation" in observation_source
    assert "canonicalize_endpoint(" not in observation_source
    assert "build_snapshot_fingerprint" not in observation_source

    snapshot_source = (nodes_root / "snapshot.py").read_text()
    assert "build_snapshot_fingerprint" in snapshot_source
    assert "canonicalize_observation" not in snapshot_source
