"""Read-only PostgreSQL queries for search indexing."""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .target_contracts import normalize_target_filters, validate_search_target

try:
    import psycopg2  # type: ignore
    from psycopg2.extras import RealDictCursor  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - optional until runtime DB operations
    class _MissingPsycopg2:
        def connect(self, _dsn: str):
            raise RuntimeError("psycopg2 is required for PostgreSQL search-indexer operations")

    psycopg2 = _MissingPsycopg2()  # type: ignore[assignment]
    RealDictCursor = object  # type: ignore[assignment]


def _connect(dsn: str):
    return psycopg2.connect(dsn)


HTTP_OBSERVATIONS_SQL = """
SELECT
    ho.id::text AS id,
    ho.program_id::text AS program_id,
    ho.endpoint_id::text AS endpoint_id,
    ho.service_id::text AS service_id,
    ho.job_id::text AS job_id,
    ho.run_id::text AS run_id,
    ho.correlation_id::text AS correlation_id,
    ho.raw_artifact_id::text AS raw_artifact_id,
    ho.body_artifact_id::text AS body_artifact_id,
    ho.method,
    ho.url,
    s.scheme,
    h.host,
    s.port,
    e.path,
    ho.status_code,
    ho.content_type,
    ho.title,
    ho.body_sha256,
    ho.body_size_bytes,
    ho.source_tool,
    ho.metadata,
    ho.observed_at,
    COALESCE(
        jsonb_agg(
            jsonb_build_object(
                'name', hh.name,
                'value', hh.value,
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
WHERE (%s::uuid IS NULL OR ho.program_id = %s::uuid)
GROUP BY ho.id, e.path, h.host, s.scheme, s.port
ORDER BY ho.observed_at DESC
LIMIT %s OFFSET %s
"""


RAW_ARTIFACTS_SQL = """
SELECT
    id::text AS id,
    program_id::text AS program_id,
    job_id::text AS job_id,
    run_id::text AS run_id,
    node_id,
    event_name,
    artifact_type,
    sha256,
    size_bytes,
    sanitized_preview,
    sanitizer_version,
    redaction_policy_version,
    sanitized_safe_for_llm,
    artifact_metadata,
    created_at
FROM raw_artifacts
WHERE (%s::uuid IS NULL OR program_id = %s::uuid)
  AND sanitized_safe_for_llm = true
  AND sanitized_preview IS NOT NULL
ORDER BY created_at DESC
LIMIT %s OFFSET %s
"""

ENDPOINTS_SQL = """
SELECT
    e.id::text AS id,
    h.program_id::text AS program_id,
    e.host_id::text AS host_id,
    e.service_id::text AS service_id,
    h.host,
    s.scheme,
    s.port,
    e.path,
    e.normalized_path,
    e.methods,
    e.status_code,
    s.technologies
FROM endpoints e
JOIN hosts h ON h.id = e.host_id
JOIN services s ON s.id = e.service_id
WHERE (%s::uuid IS NULL OR h.program_id = %s::uuid)
ORDER BY h.host, s.port, e.normalized_path, e.id
LIMIT %s OFFSET %s
"""


TECHNOLOGIES_SQL = """
SELECT
    s.id::text AS service_id,
    ip.program_id::text AS program_id,
    ip.address,
    s.scheme,
    s.port,
    s.technologies
FROM services s
JOIN ip_addresses ip ON ip.id = s.ip_id
WHERE (%s::uuid IS NULL OR ip.program_id = %s::uuid)
  AND s.technologies IS NOT NULL
  AND s.technologies <> '{}'::jsonb
ORDER BY ip.address, s.port, s.id
LIMIT %s OFFSET %s
"""


FINDINGS_SQL = """
SELECT
    f.id::text AS id,
    f.program_id::text AS program_id,
    f.vuln_type_id::text AS vuln_type_id,
    vt.code AS vuln_code,
    vt.severity,
    vt.category,
    f.host_id::text AS host_id,
    f.endpoint_id::text AS endpoint_id,
    f.parameter_id::text AS parameter_id,
    f.payload_id::text AS payload_id,
    f.execution_id::text AS execution_id,
    f.description,
    f.evidence,
    f.verified,
    f.false_positive
FROM findings f
JOIN vuln_types vt ON vt.id = f.vuln_type_id
WHERE (%s::uuid IS NULL OR f.program_id = %s::uuid)
ORDER BY f.id
LIMIT %s OFFSET %s
"""


DETECTION_SIGNALS_SQL = """
SELECT
    id::text AS id,
    event_id::text AS event_id,
    event_type,
    program_id::text AS program_id,
    job_id::text AS job_id,
    run_id::text AS run_id,
    correlation_id::text AS correlation_id,
    causation_id::text AS causation_id,
    source,
    profile,
    confidence,
    created_at
FROM event_store
WHERE (%s::uuid IS NULL OR program_id = %s::uuid)
ORDER BY created_at DESC
LIMIT %s OFFSET %s
"""


HYPOTHESES_SQL = """
SELECT
    rh.id::text AS id,
    rh.program_id::text AS program_id,
    rh.hypothesis_type,
    rh.hypothesis_fingerprint,
    rh.status,
    rh.state_version,
    rh.priority_score,
    rh.confidence,
    rh.severity_guess,
    rh.safety_level,
    rh.score_version,
    rh.inputs_hash,
    rh.source_signal_fingerprints,
    rh.duplicate_of_hypothesis_id::text AS duplicate_of_hypothesis_id,
    rh.first_seen,
    rh.last_seen,
    rh.updated_at,
    COUNT(rhe.id)::int AS evidence_count,
    COALESCE(
        jsonb_agg(
            jsonb_build_object(
                'id', rhe.id::text,
                'ref_type', rhe.ref_type,
                'ref_id', rhe.ref_id,
                'field_path', rhe.field_path,
                'role', rhe.role,
                'claim_type', rhe.claim_type,
                'claim', CASE WHEN rhe.safe_for_search THEN rhe.claim ELSE NULL END,
                'safe_excerpt', CASE WHEN rhe.safe_for_search THEN rhe.safe_excerpt ELSE NULL END,
                'safe_for_search', rhe.safe_for_search,
                'sensitivity_level', rhe.sensitivity_level
            )
            ORDER BY rhe.created_at, rhe.id
        ) FILTER (WHERE rhe.id IS NOT NULL),
        '[]'::jsonb
    ) AS evidence
FROM research_hypotheses rh
LEFT JOIN research_hypothesis_evidence rhe ON rhe.hypothesis_id = rh.id
WHERE (%s::uuid IS NULL OR rh.program_id = %s::uuid)
GROUP BY rh.id
ORDER BY rh.priority_score DESC, rh.last_seen DESC, rh.id
LIMIT %s OFFSET %s
"""


SURFACE_COMPONENT_ANALYSIS_SQL = """
SELECT
    item.id::text AS id,
    item.analysis_run_id::text AS analysis_run_id,
    item.program_id::text AS program_id,
    item.snapshot_id::text AS snapshot_id,
    run.previous_snapshot_id::text AS previous_snapshot_id,
    run.algorithm,
    run.algorithm_version,
    run.report_fingerprint,
    item.component_id,
    item.node_count,
    item.changed_node_count,
    item.structural_pressure_score,
    item.drift_score,
    item.bridge_pressure_score,
    item.outlier_score,
    item.coverage_score,
    item.exploration_priority_score,
    item.action_candidate_count,
    item.metrics_json,
    item.action_candidates_json,
    item.created_at,
    run.created_at AS analysis_created_at
FROM surface_component_analysis_items item
JOIN surface_component_analysis_runs run ON run.id = item.analysis_run_id
WHERE (%s::uuid IS NULL OR item.program_id = %s::uuid)
  AND (%s::uuid IS NULL OR item.analysis_run_id = %s::uuid)
  AND (%s::uuid IS NULL OR item.snapshot_id = %s::uuid)
ORDER BY item.exploration_priority_score DESC NULLS LAST,
         item.structural_pressure_score DESC NULLS LAST,
         item.created_at DESC,
         item.component_id ASC
LIMIT %s OFFSET %s
"""


SURFACE_DELTAS_SQL = """
SELECT
    id::text AS id,
    program_id::text AS program_id,
    from_snapshot_id::text AS from_snapshot_id,
    to_snapshot_id::text AS to_snapshot_id,
    delta_type,
    subject_type,
    subject_fingerprint,
    novelty_score,
    details_json,
    created_at
FROM surface_deltas
WHERE (%s::uuid IS NULL OR program_id = %s::uuid)
  AND (%s::uuid IS NULL OR to_snapshot_id = %s::uuid)
ORDER BY created_at DESC, novelty_score DESC, id
LIMIT %s OFFSET %s
"""

COUNT_SQL = {
    "http-observations": "SELECT count(*) FROM http_observations WHERE program_id = %s::uuid",
    "artifacts": (
        "SELECT count(*) FROM raw_artifacts "
        "WHERE program_id = %s::uuid "
        "AND sanitized_safe_for_llm = true "
        "AND sanitized_preview IS NOT NULL"
    ),
    "endpoints": (
        "SELECT count(*) FROM endpoints e "
        "JOIN hosts h ON h.id = e.host_id "
        "WHERE h.program_id = %s::uuid"
    ),
    "technologies": (
        "SELECT count(*) FROM services s "
        "JOIN ip_addresses ip ON ip.id = s.ip_id "
        "WHERE ip.program_id = %s::uuid "
        "AND s.technologies IS NOT NULL "
        "AND s.technologies <> '{}'::jsonb"
    ),
    "findings": "SELECT count(*) FROM findings WHERE program_id = %s::uuid",
    "detection-signals": "SELECT count(*) FROM event_store WHERE program_id = %s::uuid",
    "hypotheses": "SELECT count(*) FROM research_hypotheses WHERE program_id = %s::uuid",
    "surface-components": "SELECT count(*) FROM surface_component_analysis_items WHERE program_id = %s::uuid",
    "surface-deltas": "SELECT count(*) FROM surface_deltas WHERE program_id = %s::uuid",
}

SURFACE_COMPONENT_COUNT_SQL = """
SELECT count(*)
FROM surface_component_analysis_items
WHERE program_id = %s::uuid
  AND (%s::uuid IS NULL OR analysis_run_id = %s::uuid)
  AND (%s::uuid IS NULL OR snapshot_id = %s::uuid)
""".strip()

SURFACE_DELTA_COUNT_SQL = """
SELECT count(*)
FROM surface_deltas
WHERE program_id = %s::uuid
  AND (%s::uuid IS NULL OR to_snapshot_id = %s::uuid)
""".strip()

class PostgresSearchReader:
    """Read normalized source-of-truth data from PostgreSQL."""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    def fetch_http_observations(self, *, limit: int, offset: int = 0, program_id: str | None = None) -> list[dict[str, Any]]:
        return self._fetch_all(HTTP_OBSERVATIONS_SQL, limit=limit, offset=offset, program_id=program_id)

    def fetch_artifacts(self, *, limit: int, offset: int = 0, program_id: str | None = None) -> list[dict[str, Any]]:
        return self._fetch_all(RAW_ARTIFACTS_SQL, limit=limit, offset=offset, program_id=program_id)

    def fetch_endpoints(self, *, limit: int, offset: int = 0, program_id: str | None = None) -> list[dict[str, Any]]:
        return self._fetch_all(ENDPOINTS_SQL, limit=limit, offset=offset, program_id=program_id)

    def fetch_technologies(self, *, limit: int, offset: int = 0, program_id: str | None = None) -> list[dict[str, Any]]:
        return self._fetch_all(TECHNOLOGIES_SQL, limit=limit, offset=offset, program_id=program_id)

    def fetch_findings(self, *, limit: int, offset: int = 0, program_id: str | None = None) -> list[dict[str, Any]]:
        return self._fetch_all(FINDINGS_SQL, limit=limit, offset=offset, program_id=program_id)

    def fetch_detection_signals(self, *, limit: int, offset: int = 0, program_id: str | None = None) -> list[dict[str, Any]]:
        return self._fetch_all(DETECTION_SIGNALS_SQL, limit=limit, offset=offset, program_id=program_id)

    def fetch_hypotheses(self, *, limit: int, offset: int = 0, program_id: str | None = None) -> list[dict[str, Any]]:
        return self._fetch_all(HYPOTHESES_SQL, limit=limit, offset=offset, program_id=program_id)

    def fetch_surface_components(
        self,
        *,
        limit: int,
        offset: int = 0,
        program_id: str | None = None,
        analysis_run_id: str | None = None,
        snapshot_id: str | None = None,
    ) -> list[dict[str, Any]]:
        return self._fetch_surface_components(
            limit=limit,
            offset=offset,
            program_id=program_id,
            analysis_run_id=analysis_run_id,
            snapshot_id=snapshot_id,
        )

    def fetch_surface_deltas(
        self,
        *,
        limit: int,
        offset: int = 0,
        program_id: str | None = None,
        snapshot_id: str | None = None,
    ) -> list[dict[str, Any]]:
        return self._fetch_surface_deltas(
            limit=limit,
            offset=offset,
            program_id=program_id,
            snapshot_id=snapshot_id,
        )

    def count_target(self, *, target: str, program_id: str, filters: dict[str, str] | None = None) -> int:
        sql, parameters = _count_query_and_parameters(target=target, program_id=program_id, filters=filters)
        with _connect(self.dsn) as connection:
            connection.set_session(readonly=True, autocommit=True)
            with connection.cursor() as cursor:
                cursor.execute(sql, parameters)
                return int(cursor.fetchone()[0])

    def _fetch_surface_components(
        self,
        *,
        limit: int,
        offset: int,
        program_id: str | None,
        analysis_run_id: str | None,
        snapshot_id: str | None,
    ) -> list[dict[str, Any]]:
        _validate_pagination(limit=limit, offset=offset)
        with _connect(self.dsn) as connection:
            connection.set_session(readonly=True, autocommit=True)
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    SURFACE_COMPONENT_ANALYSIS_SQL,
                    (
                        program_id,
                        program_id,
                        analysis_run_id,
                        analysis_run_id,
                        snapshot_id,
                        snapshot_id,
                        limit,
                        offset,
                    ),
                )
                return [dict(row) for row in cursor.fetchall()]

    def _fetch_surface_deltas(
        self,
        *,
        limit: int,
        offset: int,
        program_id: str | None,
        snapshot_id: str | None,
    ) -> list[dict[str, Any]]:
        _validate_pagination(limit=limit, offset=offset)
        with _connect(self.dsn) as connection:
            connection.set_session(readonly=True, autocommit=True)
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    SURFACE_DELTAS_SQL,
                    (program_id, program_id, snapshot_id, snapshot_id, limit, offset),
                )
                return [dict(row) for row in cursor.fetchall()]

    def _fetch_all(self, sql: str, *, limit: int, offset: int, program_id: str | None) -> list[dict[str, Any]]:
        _validate_pagination(limit=limit, offset=offset)
        with _connect(self.dsn) as connection:
            connection.set_session(readonly=True, autocommit=True)
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(sql, (program_id, program_id, limit, offset))
                return [dict(row) for row in cursor.fetchall()]


def _count_query_and_parameters(
    *,
    target: str,
    program_id: str,
    filters: dict[str, str] | None,
) -> tuple[str, tuple[object, ...]]:
    normalized_target = validate_search_target(target)
    normalized_filters = normalize_target_filters(target=normalized_target, filters=filters)
    if normalized_target == "surface-components":
        analysis_run_id = normalized_filters.get("analysis_run_id")
        snapshot_id = normalized_filters.get("snapshot_id")
        return SURFACE_COMPONENT_COUNT_SQL, (
            program_id,
            analysis_run_id,
            analysis_run_id,
            snapshot_id,
            snapshot_id,
        )
    if normalized_target == "surface-deltas":
        snapshot_id = normalized_filters.get("snapshot_id")
        return SURFACE_DELTA_COUNT_SQL, (program_id, snapshot_id, snapshot_id)
    return COUNT_SQL[normalized_target], (program_id,)


def _validate_pagination(*, limit: int, offset: int) -> None:
    if limit <= 0:
        raise ValueError("limit must be positive")
    if offset < 0:
        raise ValueError("offset must be non-negative")


def batched_offsets(*, limit: int, batch_size: int) -> Iterable[tuple[int, int]]:
    if limit <= 0:
        return
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    offset = 0
    remaining = limit
    while remaining > 0:
        current = min(batch_size, remaining)
        yield current, offset
        offset += current
        remaining -= current
