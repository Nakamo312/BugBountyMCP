import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SURFACE_ROOT = ROOT / "services" / "surface-engine"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(SURFACE_ROOT))

from surface_engine.postgres import (  # noqa: E402
    HTTP_OBSERVATIONS_FOR_SURFACE_SQL,
    UPSERT_SURFACE_NODE_SQL,
    UPSERT_SURFACE_SNAPSHOT_SQL,
)


def test_surface_observation_reader_sql_uses_safe_shape_inputs_only():
    sql = HTTP_OBSERVATIONS_FOR_SURFACE_SQL

    assert "FROM http_observations ho" in sql
    assert "WHERE ho.program_id = %s" in sql
    assert "ho.body_sha256" in sql
    assert "ho.body_size_bytes" in sql
    assert "ho.metadata" in sql
    assert "ho.body_preview" not in sql
    assert "hh.value" not in sql
    assert "'value'" not in sql


def test_surface_writes_snapshots_and_nodes_with_idempotent_conflicts():
    assert "ON CONFLICT (program_id, snapshot_fingerprint)" in UPSERT_SURFACE_SNAPSHOT_SQL
    assert "ON CONFLICT (program_id, snapshot_id, node_fingerprint)" in UPSERT_SURFACE_NODE_SQL
    assert "features_json = EXCLUDED.features_json" in UPSERT_SURFACE_NODE_SQL
    assert "updated_at = now()" in UPSERT_SURFACE_NODE_SQL

from surface_engine.postgres import (  # noqa: E402
    FETCH_PREVIOUS_SURFACE_SNAPSHOT_SQL,
    FETCH_SURFACE_EDGES_SQL,
    FETCH_SURFACE_NODES_SQL,
    UPSERT_SURFACE_DELTA_SQL,
    UPSERT_SURFACE_EDGE_SQL,
)


def test_surface_writes_edges_and_deltas_with_idempotent_conflicts():
    assert "INSERT INTO surface_edges" in UPSERT_SURFACE_EDGE_SQL
    assert "JOIN surface_nodes dst" in UPSERT_SURFACE_EDGE_SQL
    assert "ON CONFLICT (program_id, snapshot_id, edge_fingerprint)" in UPSERT_SURFACE_EDGE_SQL
    assert "INSERT INTO surface_deltas" in UPSERT_SURFACE_DELTA_SQL
    assert "ON CONFLICT (program_id, to_snapshot_id, delta_type, subject_fingerprint)" in UPSERT_SURFACE_DELTA_SQL
    assert "FROM surface_snapshots" in FETCH_PREVIOUS_SURFACE_SNAPSHOT_SQL
    assert "FROM surface_nodes" in FETCH_SURFACE_NODES_SQL
    assert "FROM surface_edges" in FETCH_SURFACE_EDGES_SQL
