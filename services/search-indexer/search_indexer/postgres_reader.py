"""Read-only PostgreSQL queries for search indexing."""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor


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
    ho.body_preview,
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
    storage_uri,
    sha256,
    size_bytes,
    artifact_metadata,
    created_at
FROM raw_artifacts
ORDER BY created_at DESC
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
ORDER BY created_at DESC
LIMIT %s OFFSET %s
"""


class PostgresSearchReader:
    """Read normalized source-of-truth data from PostgreSQL."""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    def fetch_http_observations(self, *, limit: int, offset: int = 0) -> list[dict[str, Any]]:
        return self._fetch_all(HTTP_OBSERVATIONS_SQL, limit=limit, offset=offset)

    def fetch_artifacts(self, *, limit: int, offset: int = 0) -> list[dict[str, Any]]:
        return self._fetch_all(RAW_ARTIFACTS_SQL, limit=limit, offset=offset)

    def fetch_findings(self, *, limit: int, offset: int = 0) -> list[dict[str, Any]]:
        return self._fetch_all(FINDINGS_SQL, limit=limit, offset=offset)

    def fetch_detection_signals(self, *, limit: int, offset: int = 0) -> list[dict[str, Any]]:
        return self._fetch_all(DETECTION_SIGNALS_SQL, limit=limit, offset=offset)

    def _fetch_all(self, sql: str, *, limit: int, offset: int) -> list[dict[str, Any]]:
        with psycopg2.connect(self.dsn) as connection:
            connection.set_session(readonly=True, autocommit=True)
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(sql, (limit, offset))
                return [dict(row) for row in cursor.fetchall()]


def batched_offsets(*, limit: int, batch_size: int) -> Iterable[tuple[int, int]]:
    if limit <= 0:
        return
    offset = 0
    remaining = limit
    while remaining > 0:
        current = min(batch_size, remaining)
        yield current, offset
        offset += current
        remaining -= current
