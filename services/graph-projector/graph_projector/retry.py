from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Mapping, Protocol
from uuid import UUID

from .row_codec import fetchall as _fetchall_rows, optional_uuid_text as _optional_uuid_text


class RetryCursor(Protocol):
    def execute(self, query: str, parameters: dict[str, object] | None = None) -> object: ...
    def fetchall(self) -> list[Mapping[str, Any]]: ...


class RetryConnection(Protocol):
    def cursor(self) -> RetryCursor: ...
    def commit(self) -> object: ...
    def rollback(self) -> object: ...


GRAPH_PROJECTOR_RETRY_QUEUES = frozenset({"projection_events", "graph_fact_batches", "surface_analysis_events"})
GRAPH_PROJECTOR_RETRY_STATUSES = frozenset({"failed", "dead", "locked"})
_DEFAULT_QUEUES = tuple(sorted(GRAPH_PROJECTOR_RETRY_QUEUES))
_DEFAULT_STATUSES = ("failed", "dead")


_RESET_GRAPH_PROJECTION_EVENTS = """
WITH retry_rows AS (
    SELECT id
    FROM graph_projection_events
    WHERE status = ANY(%(statuses)s)
      AND (%(program_id)s IS NULL OR program_id = %(program_id)s)
      AND (status <> 'locked' OR locked_until IS NULL OR locked_until < %(now)s)
    ORDER BY updated_at ASC, created_at ASC
    LIMIT %(limit)s
)
UPDATE graph_projection_events
SET status = 'pending',
    attempts = 0,
    available_at = %(now)s,
    locked_by = NULL,
    locked_until = NULL,
    processed_at = NULL,
    last_error = NULL,
    updated_at = %(now)s
WHERE id IN (SELECT id FROM retry_rows)
RETURNING id;
""".strip()

_RESET_GRAPH_FACT_BATCHES = """
WITH retry_rows AS (
    SELECT id
    FROM graph_fact_batches
    WHERE status = ANY(%(statuses)s)
      AND (%(program_id)s IS NULL OR program_id = %(program_id)s)
      AND (status <> 'locked' OR locked_until IS NULL OR locked_until < %(now)s)
    ORDER BY updated_at ASC, created_at ASC
    LIMIT %(limit)s
)
UPDATE graph_fact_batches
SET status = 'pending',
    attempts = 0,
    available_at = %(now)s,
    locked_by = NULL,
    locked_until = NULL,
    applied_at = NULL,
    last_error = NULL,
    updated_at = %(now)s
WHERE id IN (SELECT id FROM retry_rows)
RETURNING id;
""".strip()

_RESET_SURFACE_COMPONENT_ANALYSIS_EVENTS = """
WITH retry_rows AS (
    SELECT id
    FROM surface_component_analysis_events
    WHERE status = ANY(%(statuses)s)
      AND (%(program_id)s IS NULL OR program_id = %(program_id)s)
      AND (status <> 'locked' OR locked_until IS NULL OR locked_until < %(now)s)
    ORDER BY updated_at ASC, created_at ASC
    LIMIT %(limit)s
)
UPDATE surface_component_analysis_events
SET status = 'pending',
    attempts = 0,
    available_at = %(now)s,
    locked_by = NULL,
    locked_until = NULL,
    processed_at = NULL,
    last_error = NULL,
    updated_at = %(now)s
WHERE id IN (SELECT id FROM retry_rows)
RETURNING id;
""".strip()


@dataclass(frozen=True)
class GraphProjectorRetryResult:
    projection_events_reset: int = 0
    graph_fact_batches_reset: int = 0
    surface_analysis_events_reset: int = 0

    @property
    def total_reset(self) -> int:
        return self.projection_events_reset + self.graph_fact_batches_reset + self.surface_analysis_events_reset


class GraphProjectorRetryService:
    """Reset durable projection rows back to pending without rebuilding source data.

    This is an operational repair path. It only changes queue state in
    PostgreSQL; it does not regenerate graph facts, apply batches to Neo4j, or
    mutate canonical inventory/action outcome rows. Locked rows are retried only
    when their lock is stale, preventing an active worker from being stolen.
    """

    def __init__(self, connection: RetryConnection) -> None:
        self._connection = connection

    def retry(
        self,
        *,
        queues: tuple[str, ...] | list[str] | set[str] | frozenset[str] | None = None,
        statuses: tuple[str, ...] | list[str] | set[str] | frozenset[str] | None = None,
        limit: int = 1000,
        program_id: UUID | str | None = None,
    ) -> GraphProjectorRetryResult:
        if limit <= 0:
            raise ValueError("limit must be positive")
        selected_queues = _normalize_queues(queues)
        selected_statuses = _normalize_statuses(statuses)

        projection_events_reset = 0
        graph_fact_batches_reset = 0
        surface_analysis_events_reset = 0
        if "projection_events" in selected_queues:
            projection_events_reset = self._reset_projection_events(
                statuses=selected_statuses,
                limit=limit,
                program_id=program_id,
            )
        if "graph_fact_batches" in selected_queues:
            graph_fact_batches_reset = self._reset_graph_fact_batches(
                statuses=selected_statuses,
                limit=limit,
                program_id=program_id,
            )
        if "surface_analysis_events" in selected_queues:
            surface_analysis_events_reset = self._reset_surface_analysis_events(
                statuses=selected_statuses,
                limit=limit,
                program_id=program_id,
            )
        return GraphProjectorRetryResult(
            projection_events_reset=projection_events_reset,
            graph_fact_batches_reset=graph_fact_batches_reset,
            surface_analysis_events_reset=surface_analysis_events_reset,
        )

    def _reset_projection_events(
        self,
        *,
        statuses: tuple[str, ...],
        limit: int,
        program_id: UUID | str | None,
    ) -> int:
        rows = self._fetchall(
            _RESET_GRAPH_PROJECTION_EVENTS,
            {
                "statuses": list(statuses),
                "limit": limit,
                "program_id": _optional_uuid_text(program_id),
                "now": datetime.now(UTC),
            },
        )
        self._connection.commit()
        return len(rows)

    def _reset_graph_fact_batches(
        self,
        *,
        statuses: tuple[str, ...],
        limit: int,
        program_id: UUID | str | None,
    ) -> int:
        rows = self._fetchall(
            _RESET_GRAPH_FACT_BATCHES,
            {
                "statuses": list(statuses),
                "limit": limit,
                "program_id": _optional_uuid_text(program_id),
                "now": datetime.now(UTC),
            },
        )
        self._connection.commit()
        return len(rows)

    def _reset_surface_analysis_events(
        self,
        *,
        statuses: tuple[str, ...],
        limit: int,
        program_id: UUID | str | None,
    ) -> int:
        rows = self._fetchall(
            _RESET_SURFACE_COMPONENT_ANALYSIS_EVENTS,
            {
                "statuses": list(statuses),
                "limit": limit,
                "program_id": _optional_uuid_text(program_id),
                "now": datetime.now(UTC),
            },
        )
        self._connection.commit()
        return len(rows)

    def _fetchall(self, query: str, parameters: dict[str, object]) -> list[Mapping[str, Any]]:
        return _fetchall_rows(self._connection, query, parameters, rollback_on_error=True)


def _normalize_queues(values: tuple[str, ...] | list[str] | set[str] | frozenset[str] | None) -> tuple[str, ...]:
    if values is None:
        return _DEFAULT_QUEUES
    normalized = tuple(dict.fromkeys(str(value).strip() for value in values))
    invalid = sorted(set(normalized) - GRAPH_PROJECTOR_RETRY_QUEUES)
    if invalid:
        raise ValueError(f"unsupported retry queue(s): {', '.join(invalid)}")
    if not normalized:
        raise ValueError("at least one retry queue must be selected")
    return normalized


def _normalize_statuses(values: tuple[str, ...] | list[str] | set[str] | frozenset[str] | None) -> tuple[str, ...]:
    if values is None:
        return _DEFAULT_STATUSES
    normalized = tuple(dict.fromkeys(str(value).strip() for value in values))
    invalid = sorted(set(normalized) - GRAPH_PROJECTOR_RETRY_STATUSES)
    if invalid:
        raise ValueError(f"unsupported retry status(es): {', '.join(invalid)}")
    if not normalized:
        raise ValueError("at least one retry status must be selected")
    return normalized
