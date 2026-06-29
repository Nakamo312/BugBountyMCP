from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from .deltas import SurfaceDeltaDraft
from .edges import SurfaceEdgeDraft
from .nodes import SurfaceNodeDraft, SurfaceSnapshotDraft

HTTP_OBSERVATIONS_FOR_SURFACE_SQL = """
SELECT
    ho.id::text AS id,
    ho.program_id::text AS program_id,
    ho.endpoint_id::text AS endpoint_id,
    ho.service_id::text AS service_id,
    ho.method,
    ho.url,
    s.scheme,
    h.host,
    s.port,
    e.path,
    ho.status_code,
    ho.content_type,
    ho.body_sha256,
    ho.body_size_bytes,
    ho.source_tool,
    ho.metadata,
    ho.observed_at,
    COALESCE(
        jsonb_agg(
            jsonb_build_object(
                'name', hh.name,
                'ordinal', hh.ordinal
            )
            ORDER BY hh.ordinal
        ) FILTER (WHERE hh.id IS NOT NULL),
        '[]'::jsonb
    ) AS headers
FROM http_observations ho
JOIN endpoints e ON e.id = ho.endpoint_id
JOIN hosts h ON h.id = e.host_id
JOIN services s ON s.id = ho.service_id
LEFT JOIN http_observation_headers hh ON hh.observation_id = ho.id
WHERE ho.program_id = %s
GROUP BY ho.id, e.path, h.host, s.scheme, s.port
ORDER BY ho.observed_at DESC, ho.id DESC
LIMIT %s OFFSET %s
"""

UPSERT_SURFACE_SNAPSHOT_SQL = """
INSERT INTO surface_snapshots (
    id,
    program_id,
    snapshot_fingerprint,
    algorithm,
    algorithm_version,
    source_window_start,
    source_window_end,
    input_watermark,
    stats_json
) VALUES (
    %(id)s,
    %(program_id)s,
    %(snapshot_fingerprint)s,
    %(algorithm)s,
    %(algorithm_version)s,
    %(source_window_start)s,
    %(source_window_end)s,
    %(input_watermark)s,
    %(stats_json)s
)
ON CONFLICT (program_id, snapshot_fingerprint)
DO UPDATE SET
    stats_json = EXCLUDED.stats_json,
    input_watermark = EXCLUDED.input_watermark
RETURNING id::text
"""


UPSERT_SURFACE_EDGE_SQL = """
INSERT INTO surface_edges (
    id,
    program_id,
    snapshot_id,
    src_node_id,
    dst_node_id,
    edge_type,
    weight,
    edge_fingerprint,
    algorithm_version,
    evidence_json
)
SELECT
    %(id)s,
    %(program_id)s,
    %(snapshot_id)s,
    src.id,
    dst.id,
    %(edge_type)s,
    %(weight)s,
    %(edge_fingerprint)s,
    %(algorithm_version)s,
    %(evidence_json)s
FROM surface_nodes src
JOIN surface_nodes dst
  ON dst.program_id = src.program_id
 AND dst.snapshot_id = src.snapshot_id
WHERE src.program_id = %(program_id)s
  AND src.snapshot_id = %(snapshot_id)s
  AND src.node_fingerprint = %(src_node_fingerprint)s
  AND dst.node_fingerprint = %(dst_node_fingerprint)s
ON CONFLICT (program_id, snapshot_id, edge_fingerprint)
DO UPDATE SET
    weight = EXCLUDED.weight,
    algorithm_version = EXCLUDED.algorithm_version,
    evidence_json = EXCLUDED.evidence_json
"""

UPSERT_SURFACE_DELTA_SQL = """
INSERT INTO surface_deltas (
    id,
    program_id,
    from_snapshot_id,
    to_snapshot_id,
    delta_type,
    subject_type,
    subject_fingerprint,
    novelty_score,
    details_json
) VALUES (
    %(id)s,
    %(program_id)s,
    %(from_snapshot_id)s,
    %(to_snapshot_id)s,
    %(delta_type)s,
    %(subject_type)s,
    %(subject_fingerprint)s,
    %(novelty_score)s,
    %(details_json)s
)
ON CONFLICT (program_id, to_snapshot_id, delta_type, subject_fingerprint)
DO UPDATE SET
    novelty_score = EXCLUDED.novelty_score,
    details_json = EXCLUDED.details_json
"""

FETCH_PREVIOUS_SURFACE_SNAPSHOT_SQL = """
SELECT id::text AS id
FROM surface_snapshots
WHERE program_id = %s
  AND id::text != %s
ORDER BY created_at DESC, id DESC
LIMIT 1
"""

FETCH_SURFACE_NODES_SQL = """
SELECT
    id::text AS id,
    node_type,
    node_fingerprint,
    feature_fingerprint,
    host,
    path,
    route_template,
    method,
    status_code,
    content_type,
    features_json
FROM surface_nodes
WHERE program_id = %s
  AND snapshot_id = %s
ORDER BY node_type ASC, node_fingerprint ASC
"""

FETCH_SURFACE_EDGES_SQL = """
SELECT
    id::text AS id,
    edge_type,
    edge_fingerprint,
    src_node_id::text AS src_node_id,
    dst_node_id::text AS dst_node_id,
    evidence_json,
    weight
FROM surface_edges
WHERE program_id = %s
  AND snapshot_id = %s
ORDER BY edge_type ASC, edge_fingerprint ASC
"""

UPSERT_SURFACE_NODE_SQL = """
INSERT INTO surface_nodes (
    id,
    program_id,
    snapshot_id,
    node_type,
    ref_type,
    ref_id,
    node_fingerprint,
    feature_fingerprint,
    feature_version,
    host,
    path,
    route_template,
    method,
    status_code,
    content_type,
    features_json,
    safe_for_search,
    first_seen,
    last_seen
) VALUES (
    %(id)s,
    %(program_id)s,
    %(snapshot_id)s,
    %(node_type)s,
    %(ref_type)s,
    %(ref_id)s,
    %(node_fingerprint)s,
    %(feature_fingerprint)s,
    %(feature_version)s,
    %(host)s,
    %(path)s,
    %(route_template)s,
    %(method)s,
    %(status_code)s,
    %(content_type)s,
    %(features_json)s,
    %(safe_for_search)s,
    %(first_seen)s,
    %(last_seen)s
)
ON CONFLICT (program_id, snapshot_id, node_fingerprint)
DO UPDATE SET
    ref_type = COALESCE(surface_nodes.ref_type, EXCLUDED.ref_type),
    ref_id = COALESCE(surface_nodes.ref_id, EXCLUDED.ref_id),
    feature_fingerprint = EXCLUDED.feature_fingerprint,
    feature_version = EXCLUDED.feature_version,
    host = EXCLUDED.host,
    path = EXCLUDED.path,
    route_template = EXCLUDED.route_template,
    method = EXCLUDED.method,
    status_code = EXCLUDED.status_code,
    content_type = EXCLUDED.content_type,
    features_json = EXCLUDED.features_json,
    safe_for_search = EXCLUDED.safe_for_search,
    first_seen = LEAST(surface_nodes.first_seen, EXCLUDED.first_seen),
    last_seen = GREATEST(surface_nodes.last_seen, EXCLUDED.last_seen),
    updated_at = now()
"""


class PostgresSurfaceStore:
    """PostgreSQL source-of-truth access for Surface Map V1."""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    def fetch_http_observations(self, *, program_id: str, limit: int, offset: int = 0) -> list[dict[str, Any]]:
        psycopg2, RealDictCursor, _ = _load_psycopg2()
        with psycopg2.connect(self.dsn) as connection:
            connection.set_session(readonly=True, autocommit=True)
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(HTTP_OBSERVATIONS_FOR_SURFACE_SQL, (program_id, limit, offset))
                return [dict(row) for row in cursor.fetchall()]

    def upsert_snapshot(self, snapshot: SurfaceSnapshotDraft) -> str:
        psycopg2, RealDictCursor, Json = _load_psycopg2()
        snapshot_id = _snapshot_uuid(snapshot)
        params = {
            "id": snapshot_id,
            "program_id": snapshot.program_id,
            "snapshot_fingerprint": snapshot.snapshot_fingerprint,
            "algorithm": snapshot.algorithm,
            "algorithm_version": snapshot.algorithm_version,
            "source_window_start": snapshot.source_window_start,
            "source_window_end": snapshot.source_window_end,
            "input_watermark": snapshot.input_watermark,
            "stats_json": Json(snapshot.stats_json),
        }
        with psycopg2.connect(self.dsn) as connection:
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(UPSERT_SURFACE_SNAPSHOT_SQL, params)
                row = cursor.fetchone()
                connection.commit()
                return str(row["id"])

    def upsert_nodes(self, *, snapshot_id: str, nodes: Iterable[SurfaceNodeDraft]) -> int:
        psycopg2, _, Json = _load_psycopg2()
        node_list = list(nodes)
        if not node_list:
            return 0
        with psycopg2.connect(self.dsn) as connection:
            with connection.cursor() as cursor:
                for node in node_list:
                    cursor.execute(
                        UPSERT_SURFACE_NODE_SQL,
                        _node_params(snapshot_id=snapshot_id, node=node, json_wrapper=Json),
                    )
                connection.commit()
        return len(node_list)


    def upsert_edges(self, *, snapshot_id: str, edges: Iterable[SurfaceEdgeDraft]) -> int:
        psycopg2, _, Json = _load_psycopg2()
        edge_list = list(edges)
        if not edge_list:
            return 0
        with psycopg2.connect(self.dsn) as connection:
            with connection.cursor() as cursor:
                for edge in edge_list:
                    cursor.execute(
                        UPSERT_SURFACE_EDGE_SQL,
                        _edge_params(snapshot_id=snapshot_id, edge=edge, json_wrapper=Json),
                    )
                connection.commit()
        return len(edge_list)

    def upsert_deltas(self, deltas: Iterable[SurfaceDeltaDraft]) -> int:
        psycopg2, _, Json = _load_psycopg2()
        delta_list = list(deltas)
        if not delta_list:
            return 0
        with psycopg2.connect(self.dsn) as connection:
            with connection.cursor() as cursor:
                for delta in delta_list:
                    cursor.execute(UPSERT_SURFACE_DELTA_SQL, _delta_params(delta=delta, json_wrapper=Json))
                connection.commit()
        return len(delta_list)

    def fetch_previous_snapshot_id(self, *, program_id: str, current_snapshot_id: str) -> str | None:
        psycopg2, RealDictCursor, _ = _load_psycopg2()
        with psycopg2.connect(self.dsn) as connection:
            connection.set_session(readonly=True, autocommit=True)
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(FETCH_PREVIOUS_SURFACE_SNAPSHOT_SQL, (program_id, current_snapshot_id))
                row = cursor.fetchone()
                return str(row["id"]) if row else None

    def fetch_snapshot_nodes(self, *, program_id: str, snapshot_id: str | None) -> list[dict[str, Any]]:
        if snapshot_id is None:
            return []
        psycopg2, RealDictCursor, _ = _load_psycopg2()
        with psycopg2.connect(self.dsn) as connection:
            connection.set_session(readonly=True, autocommit=True)
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(FETCH_SURFACE_NODES_SQL, (program_id, snapshot_id))
                return [dict(row) for row in cursor.fetchall()]

    def fetch_snapshot_edges(self, *, program_id: str, snapshot_id: str | None) -> list[dict[str, Any]]:
        if snapshot_id is None:
            return []
        psycopg2, RealDictCursor, _ = _load_psycopg2()
        with psycopg2.connect(self.dsn) as connection:
            connection.set_session(readonly=True, autocommit=True)
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(FETCH_SURFACE_EDGES_SQL, (program_id, snapshot_id))
                return [dict(row) for row in cursor.fetchall()]


def _load_psycopg2():
    try:
        import psycopg2
        from psycopg2.extras import Json, RealDictCursor
    except ImportError as exc:  # pragma: no cover - depends on runtime image
        raise RuntimeError("surface-engine database commands require psycopg2-binary") from exc
    return psycopg2, RealDictCursor, Json


def _snapshot_uuid(snapshot: SurfaceSnapshotDraft) -> str:
    return str(uuid5(NAMESPACE_URL, f"surface-snapshot:{snapshot.program_id}:{snapshot.snapshot_fingerprint}"))


def _node_uuid(*, snapshot_id: str, node: SurfaceNodeDraft) -> str:
    return str(uuid5(NAMESPACE_URL, f"surface-node:{snapshot_id}:{node.node_fingerprint}"))


def _edge_uuid(*, snapshot_id: str, edge: SurfaceEdgeDraft) -> str:
    return str(uuid5(NAMESPACE_URL, f"surface-edge:{snapshot_id}:{edge.edge_fingerprint}"))


def _delta_uuid(delta: SurfaceDeltaDraft) -> str:
    return str(
        uuid5(
            NAMESPACE_URL,
            f"surface-delta:{delta.program_id}:{delta.to_snapshot_id}:{delta.delta_type}:{delta.subject_fingerprint}",
        )
    )


def _node_params(*, snapshot_id: str, node: SurfaceNodeDraft, json_wrapper: Any) -> dict[str, Any]:
    return {
        "id": _node_uuid(snapshot_id=snapshot_id, node=node),
        "program_id": node.program_id,
        "snapshot_id": snapshot_id,
        "node_type": node.node_type,
        "ref_type": node.ref_type,
        "ref_id": node.ref_id,
        "node_fingerprint": node.node_fingerprint,
        "feature_fingerprint": node.feature_fingerprint,
        "feature_version": node.feature_version,
        "host": node.host,
        "path": node.path,
        "route_template": node.route_template,
        "method": node.method,
        "status_code": node.status_code,
        "content_type": node.content_type,
        "features_json": json_wrapper(node.features_json),
        "safe_for_search": node.safe_for_search,
        "first_seen": node.first_seen,
        "last_seen": node.last_seen,
    }



def _edge_params(*, snapshot_id: str, edge: SurfaceEdgeDraft, json_wrapper: Any) -> dict[str, Any]:
    return {
        "id": _edge_uuid(snapshot_id=snapshot_id, edge=edge),
        "program_id": edge.program_id,
        "snapshot_id": snapshot_id,
        "src_node_fingerprint": edge.src_node_fingerprint,
        "dst_node_fingerprint": edge.dst_node_fingerprint,
        "edge_type": edge.edge_type,
        "weight": edge.weight,
        "edge_fingerprint": edge.edge_fingerprint,
        "algorithm_version": edge.algorithm_version,
        "evidence_json": json_wrapper(edge.evidence_json),
    }


def _delta_params(*, delta: SurfaceDeltaDraft, json_wrapper: Any) -> dict[str, Any]:
    return {
        "id": _delta_uuid(delta),
        "program_id": delta.program_id,
        "from_snapshot_id": delta.from_snapshot_id,
        "to_snapshot_id": delta.to_snapshot_id,
        "delta_type": delta.delta_type,
        "subject_type": delta.subject_type,
        "subject_fingerprint": delta.subject_fingerprint,
        "novelty_score": delta.novelty_score,
        "details_json": json_wrapper(delta.details_json),
    }
