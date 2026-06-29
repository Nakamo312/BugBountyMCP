from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4
from tests.infrastructure.graph_projector_cli_test_helpers import graph_projector_cli_source


def _symbols():
    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.rebuild import GraphRebuildService

    return GraphRebuildService


class FakeCursor:
    def __init__(self, connection: "FakeConnection") -> None:
        self.connection = connection
        self.query = ""
        self.parameters = {}

    def execute(self, query: str, parameters: dict[str, object] | None = None) -> object:
        self.query = query
        self.parameters = parameters or {}
        self.connection.queries.append(query)
        return None

    def fetchall(self) -> list[dict[str, object]]:
        if "FROM raw_artifacts" in self.query:
            return [self.connection.raw_artifact_row]
        if "FROM host_ips" in self.query:
            return self.connection.canonical_inventory_rows
        if "FROM http_observations" in self.query:
            return self.connection.http_observation_rows
        if "FROM javascript_references" in self.query:
            return self.connection.javascript_reference_rows
        if "FROM action_outcomes" in self.query:
            return self.connection.action_outcome_rows
        if "FROM surface_snapshots" in self.query:
            return self.connection.surface_map_rows
        raise AssertionError(f"unexpected query: {self.query}")


class FakeConnection:
    def __init__(self) -> None:
        program_id = uuid4()
        run_id = uuid4()
        raw_artifact_id = uuid4()
        service_id = uuid4()
        self.raw_artifact_row = {
            "id": raw_artifact_id,
            "program_id": program_id,
            "job_id": uuid4(),
            "run_id": run_id,
            "node_id": "httpx",
            "event_name": "httpx.completed",
            "artifact_type": "raw_tool_output",
            "storage_uri": "raw://artifact/httpx.ndjson",
            "sha256": "a" * 64,
            "size_bytes": 100,
            "artifact_metadata": {},
            "created_at": None,
        }
        self.http_observation_rows = [
            {
                "observation_id": uuid4(),
                "program_id": program_id,
                "run_id": run_id,
                "raw_artifact_id": raw_artifact_id,
                "source_tool": "httpx",
                "method": "GET",
                "url": "https://api.example.com/v1/users/123",
                "status_code": 200,
                "content_type": "application/json",
                "observed_at": None,
                "endpoint_id": uuid4(),
                "path": "/v1/users/123",
                "normalized_path": "/v1/users/{id}",
                "host_id": uuid4(),
                "hostname": "api.example.com",
                "service_id": service_id,
                "scheme": "https",
                "port": 443,
                "ip_id": uuid4(),
                "ip_address": "203.0.113.10",
            }
        ]
        self.canonical_inventory_rows = [
            {
                "program_id": program_id,
                "host_id": uuid4(),
                "hostname": "api.example.com",
                "ip_id": uuid4(),
                "ip_address": "203.0.113.10",
                "host_ip_source": "dnsx",
                "service_id": service_id,
                "service_scheme": "https",
                "service_port": 443,
                "technologies": {"nginx": True},
            }
        ]
        self.action_outcome_rows = [
            {
                "id": uuid4(),
                "program_id": program_id,
                "campaign_id": uuid4(),
                "action_id": uuid4(),
                "job_id": uuid4(),
                "run_id": run_id,
                "capability_id": "web.http_probe",
                "profile_id": "passive-default",
                "node_id": "httpx",
                "event_name": "httpx.completed",
                "status": "completed",
                "terminal_outcome": "completed",
                "attempt": 1,
                "target_count": 1,
                "started_at": None,
                "finished_at": None,
                "duration_ms": 1000,
                "error_count": 0,
                "raw_artifact_count": 1,
                "raw_artifact_bytes": 100,
                "observed_hosts_count": 1,
                "observed_services_count": 1,
                "observed_endpoints_count": 1,
                "http_observation_count": 1,
                "javascript_reference_count": 0,
                "manual_interest": None,
                "manual_stop": None,
                "continued_by_followup": None,
                "report_created": None,
                "triage_outcome": None,
                "information_gain_score": 2.0,
                "score_version": "action-outcome-information-gain.v1",
                "updated_at": None,
            }
        ]
        self.surface_map_rows = [
            {
                "program_id": program_id,
                "snapshot_id": uuid4(),
                "snapshot_fingerprint": "s" * 64,
                "snapshot_algorithm_version": "surface-map-v1",
                "input_watermark": "wm",
                "node_id": uuid4(),
                "node_type": "endpoint",
                "node_fingerprint": "n1",
                "feature_fingerprint": "f1",
                "method": "GET",
                "status_code": 200,
                "content_type": "application/json",
                "edge_id": uuid4(),
                "edge_type": "HAS_ROUTE_SHAPE",
                "edge_fingerprint": "e1",
                "weight": 1.0,
                "edge_algorithm_version": "surface-edge-v1",
                "src_node_fingerprint": "n1",
                "dst_node_fingerprint": "n2",
                "delta_id": uuid4(),
                "from_snapshot_id": None,
                "delta_type": "node_introduced",
                "delta_subject_type": "endpoint",
                "delta_subject_fingerprint": "n1",
                "novelty_score": 50,
            }
        ]
        self.javascript_reference_rows = [
            {
                "javascript_reference_id": uuid4(),
                "program_id": program_id,
                "run_id": run_id,
                "raw_artifact_id": raw_artifact_id,
                "source_tool": "linkfinder",
                "source_url": "https://app.example.com/static/app.js?v=123",
                "referenced_url": "https://api.example.com/v1/users/123?token=secret",
                "reference_type": "endpoint",
                "observed_at": None,
                "endpoint_id": uuid4(),
                "path": "/v1/users/123",
                "normalized_path": "/v1/users/{id}",
                "host_id": uuid4(),
                "hostname": "api.example.com",
                "service_id": service_id,
                "scheme": "https",
                "port": 443,
                "ip_id": uuid4(),
                "ip_address": "203.0.113.10",
            }
        ]
        self.queries: list[str] = []

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def commit(self) -> object:
        return None

    def rollback(self) -> object:
        return None


class RecordingStore:
    def __init__(self) -> None:
        self.calls: list[tuple[object, str | None, bool]] = []

    def enqueue(self, batch, *, dedupe_key: str | None = None, reset_existing: bool = False):
        self.calls.append((batch, dedupe_key, reset_existing))
        return uuid4()


def test_graph_rebuild_requeues_canonical_sources_without_raw_body_reads() -> None:
    GraphRebuildService = _symbols()
    connection = FakeConnection()
    store = RecordingStore()

    result = GraphRebuildService(connection=connection, store=store).rebuild(limit=100)

    assert result.raw_artifacts_scanned == 1
    assert result.canonical_inventory_programs_scanned == 1
    assert result.http_observation_sources_scanned == 1
    assert result.javascript_reference_sources_scanned == 1
    assert result.action_outcomes_scanned == 1
    assert result.surface_snapshots_scanned == 1
    assert result.enqueued == 6
    assert [call[2] for call in store.calls] == [True, True, True, True, True, True]
    assert store.calls[0][1].startswith("rebuild:raw-artifact-metadata:")
    assert store.calls[1][1].startswith("rebuild:canonical-inventory:")
    assert store.calls[2][1].startswith("rebuild:http-observations:")
    assert store.calls[3][1].startswith("rebuild:javascript-references:")
    assert store.calls[4][1].startswith("rebuild:action-outcome:")
    assert store.calls[5][1].startswith("rebuild:surface-map:")
    assert any("FROM host_ips" in query for query in connection.queries)
    assert any("JOIN hosts" in query for query in connection.queries)
    assert any("JOIN ip_addresses" in query for query in connection.queries)
    assert any("LEFT JOIN services" in query for query in connection.queries)
    assert any("ho.source_tool IS NOT NULL" in query for query in connection.queries)
    assert any("jr.source_tool IS NOT NULL" in query for query in connection.queries)
    assert any("FROM surface_snapshots" in query for query in connection.queries)
    removed_inventory_observation_table = "asset_" + "observations"
    assert all(removed_inventory_observation_table not in query for query in connection.queries)
    assert all("source_tool = ANY" not in query for query in connection.queries)
    assert all("body" not in query.lower() for query in connection.queries)


def test_graph_rebuild_can_refresh_only_mutable_action_outcomes() -> None:
    GraphRebuildService = _symbols()
    connection = FakeConnection()
    store = RecordingStore()

    result = GraphRebuildService(connection=connection, store=store).rebuild(
        limit=100,
        sources={"action_outcomes"},
    )

    assert result.raw_artifacts_scanned == 0
    assert result.canonical_inventory_programs_scanned == 0
    assert result.http_observation_sources_scanned == 0
    assert result.javascript_reference_sources_scanned == 0
    assert result.action_outcomes_scanned == 1
    assert result.surface_snapshots_scanned == 0
    assert result.enqueued == 1
    assert store.calls[0][1].startswith("rebuild:action-outcome:")
    assert all("FROM action_outcomes" in query for query in connection.queries)


def test_graph_rebuild_rejects_unknown_source() -> None:
    import pytest

    GraphRebuildService = _symbols()
    connection = FakeConnection()
    store = RecordingStore()

    with pytest.raises(ValueError, match="unknown graph rebuild sources"):
        GraphRebuildService(connection=connection, store=store).rebuild(
            limit=100,
            sources={"not-a-source"},
        )


def test_graph_projector_cli_exposes_rebuild_command() -> None:
    source = graph_projector_cli_source()

    assert "rebuild" in source
    assert "GraphRebuildService" in source
    assert "--source" in source
    assert "GRAPH_REBUILD_SOURCES" in source
