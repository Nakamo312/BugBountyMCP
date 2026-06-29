from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Mapping, Protocol
from uuid import UUID

from ..row_codec import optional_uuid_text


class HttpObservationClaimCursor(Protocol):
    def execute(self, query: str, parameters: dict[str, object] | None = None) -> object: ...
    def fetchall(self) -> list[Mapping[str, Any]]: ...


class HttpObservationClaimConnection(Protocol):
    def cursor(self) -> HttpObservationClaimCursor: ...


HTTP_OBSERVATION_CLAIM_ROWS_SQL = """
WITH next_events AS (
    SELECT id
    FROM graph_projection_events
    WHERE source_type = 'raw_artifact'
      AND event_type = 'http_observations_ready'
      AND status IN ('pending', 'failed')
      AND available_at <= %(now)s
      AND attempts < %(max_attempts)s
      AND (locked_until IS NULL OR locked_until < %(now)s)
      AND (%(program_id)s IS NULL OR program_id = %(program_id)s)
    ORDER BY available_at ASC, created_at ASC
    FOR UPDATE SKIP LOCKED
    LIMIT %(limit)s
), locked_events AS (
    UPDATE graph_projection_events
    SET status = 'locked',
        locked_by = %(worker_id)s,
        locked_until = %(locked_until)s,
        attempts = attempts + 1,
        updated_at = %(now)s,
        last_error = NULL
    WHERE id IN (SELECT id FROM next_events)
    RETURNING id, program_id, source_id, attempts
)
SELECT
    locked_events.id AS projection_event_id,
    locked_events.attempts AS projection_event_attempts,
    locked_events.source_id AS event_raw_artifact_id,
    ho.id AS observation_id,
    ho.program_id,
    ho.run_id,
    ho.raw_artifact_id,
    ho.source_tool,
    ho.method,
    ho.url,
    ho.status_code,
    ho.content_type,
    ho.observed_at,
    e.id AS endpoint_id,
    e.path,
    e.normalized_path,
    h.id AS host_id,
    h.host AS hostname,
    s.id AS service_id,
    s.scheme,
    s.port,
    ip.id AS ip_id,
    ip.address AS ip_address
FROM locked_events
LEFT JOIN http_observations ho
    ON ho.raw_artifact_id = locked_events.source_id
   AND ho.run_id IS NOT NULL
   AND ho.raw_artifact_id IS NOT NULL
   AND ho.source_tool IS NOT NULL
   AND ho.source_tool != ''
LEFT JOIN endpoints e ON e.id = ho.endpoint_id
LEFT JOIN hosts h ON h.id = e.host_id
LEFT JOIN services s ON s.id = ho.service_id
LEFT JOIN ip_addresses ip ON ip.id = s.ip_id
LEFT JOIN host_ips hi ON hi.host_id = h.id AND hi.ip_id = ip.id
ORDER BY locked_events.id ASC, ho.observed_at ASC, ho.id ASC;
""".strip()


def claim_http_observation_rows(
    connection: HttpObservationClaimConnection,
    *,
    limit: int,
    program_id: UUID | str | None,
    worker_id: str,
    lock_seconds: int,
    max_attempts: int,
) -> list[Mapping[str, Any]]:
    now = datetime.now(UTC)
    cursor = connection.cursor()
    cursor.execute(
        HTTP_OBSERVATION_CLAIM_ROWS_SQL,
        claim_http_observation_rows_values(
            limit=limit,
            program_id=program_id,
            now=now,
            locked_until=now + timedelta(seconds=lock_seconds),
            worker_id=worker_id,
            max_attempts=max_attempts,
        ),
    )
    rows = list(cursor.fetchall())
    if hasattr(connection, "commit"):
        connection.commit()  # type: ignore[attr-defined]
    return rows


def claim_http_observation_rows_values(
    *,
    limit: int,
    program_id: UUID | str | None,
    now: datetime,
    locked_until: datetime,
    worker_id: str,
    max_attempts: int,
) -> dict[str, object]:
    return {
        "limit": limit,
        "program_id": optional_uuid_text(program_id),
        "now": now,
        "locked_until": locked_until,
        "worker_id": worker_id,
        "max_attempts": max_attempts,
    }
