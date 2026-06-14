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
