from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Mapping, Protocol
from uuid import UUID

from ..row_codec import optional_uuid_text


class RawArtifactClaimCursor(Protocol):
    def execute(self, query: str, parameters: dict[str, object] | None = None) -> object: ...
    def fetchall(self) -> list[Mapping[str, Any]]: ...


class RawArtifactClaimConnection(Protocol):
    def cursor(self) -> RawArtifactClaimCursor: ...


RAW_ARTIFACT_CLAIM_SQL = """
WITH next_events AS (
    SELECT id
    FROM graph_projection_events
    WHERE source_type = 'raw_artifact'
      AND event_type = 'raw_artifact_created'
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
    RETURNING id, source_id, attempts
)
SELECT
    locked_events.id AS projection_event_id,
    locked_events.attempts AS projection_event_attempts,
    raw_artifacts.id,
    raw_artifacts.program_id,
    raw_artifacts.job_id,
    raw_artifacts.run_id,
    raw_artifacts.node_id,
    raw_artifacts.event_name,
    raw_artifacts.artifact_type,
    raw_artifacts.storage_uri,
    raw_artifacts.sha256,
    raw_artifacts.size_bytes,
    raw_artifacts.artifact_metadata,
    raw_artifacts.created_at
FROM locked_events
JOIN raw_artifacts ON raw_artifacts.id = locked_events.source_id
WHERE raw_artifacts.run_id IS NOT NULL
ORDER BY raw_artifacts.created_at ASC, raw_artifacts.id ASC;
""".strip()


def claim_raw_artifact_rows(
    connection: RawArtifactClaimConnection,
    *,
    limit: int,
    program_id: UUID | str | None,
    worker_id: str,
    lock_seconds: int,
    max_attempts: int,
) -> list[Mapping[str, Any]]:
    cursor = connection.cursor()
    cursor.execute(
        RAW_ARTIFACT_CLAIM_SQL,
        raw_artifact_claim_values(
            limit=limit,
            program_id=program_id,
            worker_id=worker_id,
            lock_seconds=lock_seconds,
            max_attempts=max_attempts,
        ),
    )
    rows = list(cursor.fetchall())
    if hasattr(connection, "commit"):
        connection.commit()  # type: ignore[attr-defined]
    return rows


def raw_artifact_claim_values(
    *,
    limit: int,
    program_id: UUID | str | None,
    worker_id: str,
    lock_seconds: int,
    max_attempts: int,
) -> dict[str, object]:
    now = datetime.now(UTC)
    return {
        "limit": limit,
        "program_id": optional_uuid_text(program_id),
        "now": now,
        "locked_until": now + timedelta(seconds=lock_seconds),
        "worker_id": worker_id,
        "max_attempts": max_attempts,
    }
