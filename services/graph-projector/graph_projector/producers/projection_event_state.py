from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID


class ProjectionEventStateCursor(Protocol):
    def execute(self, query: str, parameters: dict[str, object] | None = None) -> object: ...


class ProjectionEventStateConnection(Protocol):
    def cursor(self) -> ProjectionEventStateCursor: ...


_MARK_GRAPH_PROJECTION_EVENT_PROCESSED = """
UPDATE graph_projection_events
SET status = 'processed',
    processed_at = %(now)s,
    updated_at = %(now)s,
    locked_by = NULL,
    locked_until = NULL,
    last_error = NULL
WHERE id = %(event_id)s
  AND status = 'locked'
  AND locked_by = %(worker_id)s;
""".strip()

_MARK_GRAPH_PROJECTION_EVENT_FAILED = """
UPDATE graph_projection_events
SET status = %(status)s,
    updated_at = %(now)s,
    locked_by = NULL,
    locked_until = NULL,
    last_error = %(error)s
WHERE id = %(event_id)s
  AND status = 'locked'
  AND locked_by = %(worker_id)s;
""".strip()


class ProjectionEventStateWriter:
    """Own graph_projection_events state transitions after a producer claims a lease."""

    def __init__(self, connection: ProjectionEventStateConnection, *, worker_id: str) -> None:
        self._connection = connection
        self._worker_id = worker_id

    def mark_processed(self, event_id: UUID) -> None:
        now = datetime.now(UTC)
        cursor = self._connection.cursor()
        cursor.execute(
            _MARK_GRAPH_PROJECTION_EVENT_PROCESSED,
            {"event_id": event_id, "now": now, "worker_id": self._worker_id},
        )
        self._commit_if_supported()

    def mark_failed(self, event_id: UUID, *, error: str, dead: bool, max_error_chars: int | None = None) -> None:
        now = datetime.now(UTC)
        cursor = self._connection.cursor()
        cursor.execute(
            _MARK_GRAPH_PROJECTION_EVENT_FAILED,
            {
                "event_id": event_id,
                "status": "dead" if dead else "failed",
                "now": now,
                "error": _bounded_error(error, max_error_chars=max_error_chars),
                "worker_id": self._worker_id,
            },
        )
        self._commit_if_supported()

    def _commit_if_supported(self) -> None:
        commit = getattr(self._connection, "commit", None)
        if callable(commit):
            commit()


def _bounded_error(error: str, *, max_error_chars: int | None) -> str:
    if max_error_chars is None:
        return error
    if max_error_chars <= 0:
        raise ValueError("max_error_chars must be positive when provided")
    return error[:max_error_chars]
