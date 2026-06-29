"""Operational repair for the OpenSearch projection event queue."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Mapping, Protocol
from uuid import UUID

from .target_contracts import validate_optional_search_target


class RetryCursor(Protocol):
    def execute(self, query: str, parameters: dict[str, object] | None = None) -> object: ...
    def fetchall(self) -> list[Mapping[str, Any]]: ...


class RetryConnection(Protocol):
    def cursor(self) -> RetryCursor: ...
    def commit(self) -> object: ...
    def rollback(self) -> object: ...


SEARCH_INDEXER_RETRY_STATUSES = frozenset({"failed", "dead", "locked"})
_DEFAULT_STATUSES = ("failed", "dead")


@dataclass(frozen=True)
class SearchIndexerRetryResult:
    events_reset: int = 0

    @property
    def total_reset(self) -> int:
        return self.events_reset


class SearchIndexerRetryService:
    """Reset durable OpenSearch projection events back to pending.

    This does not reindex, enqueue, or mutate OpenSearch. Locked rows are reset
    only when their lock is stale.
    """

    def __init__(self, connection: RetryConnection) -> None:
        self._connection = connection

    def retry(
        self,
        *,
        statuses: tuple[str, ...] | list[str] | set[str] | frozenset[str] | None = None,
        limit: int = 1000,
        program_id: UUID | str | None = None,
        target: str | None = None,
    ) -> SearchIndexerRetryResult:
        if limit <= 0:
            raise ValueError("limit must be positive")
        target = validate_optional_search_target(target)
        selected_statuses = _normalize_statuses(statuses)
        rows = self._fetchall(
            """
WITH retry_rows AS (
    SELECT id
    FROM search_projection_events
    WHERE status = ANY(%(statuses)s)
      AND (%(program_id)s IS NULL OR program_id = %(program_id)s::uuid)
      AND (%(target)s IS NULL OR target = %(target)s)
      AND (
          status != 'locked'
          OR locked_until IS NULL
          OR locked_until < %(now)s
      )
    ORDER BY updated_at ASC, created_at ASC
    LIMIT %(limit)s
    FOR UPDATE SKIP LOCKED
)
UPDATE search_projection_events
SET status = 'pending',
    attempts = 0,
    available_at = %(now)s,
    locked_by = NULL,
    locked_until = NULL,
    last_error = NULL,
    processed_at = NULL,
    result_json = '{}'::jsonb,
    updated_at = %(now)s
WHERE id IN (SELECT id FROM retry_rows)
RETURNING id;
""".strip(),
            {
                "statuses": list(selected_statuses),
                "program_id": None if program_id is None else str(program_id),
                "target": target,
                "limit": limit,
                "now": datetime.now(UTC),
            },
        )
        return SearchIndexerRetryResult(events_reset=len(rows))

    def _fetchall(self, query: str, parameters: dict[str, object]) -> list[Mapping[str, Any]]:
        cursor = self._cursor()
        cursor.execute(query, parameters)
        return list(cursor.fetchall())

    def _cursor(self) -> RetryCursor:
        cursor = self._connection.cursor()
        if hasattr(cursor, "__enter__"):
            return cursor.__enter__()
        return cursor


def _normalize_statuses(
    statuses: tuple[str, ...] | list[str] | set[str] | frozenset[str] | None,
) -> tuple[str, ...]:
    if statuses is None:
        return _DEFAULT_STATUSES
    normalized = tuple(sorted({status.strip() for status in statuses if status and status.strip()}))
    invalid = set(normalized) - SEARCH_INDEXER_RETRY_STATUSES
    if invalid:
        raise ValueError(f"unsupported search-indexer retry statuses: {', '.join(sorted(invalid))}")
    if not normalized:
        raise ValueError("at least one retry status is required")
    return normalized
