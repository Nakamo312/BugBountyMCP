from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Mapping, Protocol
from uuid import UUID

from ..row_codec import optional_uuid_text


class JavaScriptReferenceClaimCursor(Protocol):
    def execute(self, query: str, parameters: dict[str, object] | None = None) -> object: ...
    def fetchall(self) -> list[Mapping[str, Any]]: ...


class JavaScriptReferenceClaimConnection(Protocol):
    def cursor(self) -> JavaScriptReferenceClaimCursor: ...


JAVASCRIPT_REFERENCE_CLAIM_ROWS_SQL = """
WITH next_events AS (
    SELECT id
    FROM graph_projection_events
    WHERE source_type = 'raw_artifact'
      AND event_type = 'javascript_references_ready'
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
    jr.id AS javascript_reference_id,
    jr.program_id,
    jr.run_id,
    jr.raw_artifact_id,
    jr.source_tool,
    jr.source_url,
    jr.referenced_url,
    jr.reference_type,
    jr.observed_at,
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
LEFT JOIN javascript_references jr
    ON jr.raw_artifact_id = locked_events.source_id
   AND jr.run_id IS NOT NULL
   AND jr.raw_artifact_id IS NOT NULL
   AND jr.source_tool IS NOT NULL
   AND jr.source_tool != ''
LEFT JOIN endpoints e ON e.id = jr.endpoint_id
LEFT JOIN hosts h ON h.id = e.host_id
LEFT JOIN services s ON s.id = jr.service_id
LEFT JOIN ip_addresses ip ON ip.id = s.ip_id
ORDER BY locked_events.id ASC, jr.observed_at ASC, jr.id ASC;
""".strip()


def claim_javascript_reference_rows(
    connection: JavaScriptReferenceClaimConnection,
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
        JAVASCRIPT_REFERENCE_CLAIM_ROWS_SQL,
        claim_javascript_reference_rows_values(
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


def claim_javascript_reference_rows_values(
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
