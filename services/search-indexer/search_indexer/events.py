"""Durable OpenSearch projection events for incremental indexing."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from time import sleep as default_sleep
from typing import Any, Callable, Mapping
from uuid import UUID, uuid4

from .reindex import run_reindex
from .settings import Settings
from .target_contracts import (
    normalize_target_filters,
    validate_search_projection_event_contract,
    validate_surface_projection_target,
)

SEARCH_SURFACE_COMPONENTS_SOURCE = "surface_component_analysis_run"
SEARCH_SURFACE_DELTAS_SOURCE = "surface_snapshot"

_SEARCH_PROJECTION_EVENT_INSERT_RESET = """
INSERT INTO search_projection_events (
    id,
    program_id,
    target,
    source_type,
    source_id,
    filters_json,
    dedupe_key
)
VALUES (%s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (dedupe_key) DO UPDATE
SET filters_json = EXCLUDED.filters_json,
    status = 'pending',
    attempts = 0,
    available_at = now(),
    locked_by = NULL,
    locked_until = NULL,
    processed_at = NULL,
    last_error = NULL,
    result_json = '{}'::jsonb,
    updated_at = now()
RETURNING id
""".strip()

_SEARCH_PROJECTION_EVENT_INSERT_KEEP_EXISTING = """
INSERT INTO search_projection_events (
    id,
    program_id,
    target,
    source_type,
    source_id,
    filters_json,
    dedupe_key
)
VALUES (%s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (dedupe_key) DO UPDATE
SET updated_at = search_projection_events.updated_at
RETURNING id
""".strip()


def _enqueue_statement(*, reset_existing: bool) -> str:
    return (
        _SEARCH_PROJECTION_EVENT_INSERT_RESET
        if reset_existing
        else _SEARCH_PROJECTION_EVENT_INSERT_KEEP_EXISTING
    )


def _load_psycopg2():
    try:
        import psycopg2  # type: ignore
        from psycopg2.extras import Json, RealDictCursor  # type: ignore
    except ModuleNotFoundError as exc:  # pragma: no cover - runtime dependency guard
        raise RuntimeError("psycopg2 is required for search projection event queue operations") from exc
    return psycopg2, Json, RealDictCursor


@dataclass(frozen=True, slots=True)
class SearchProjectionEvent:
    id: UUID
    program_id: str
    target: str
    source_type: str
    source_id: str | None
    filters_json: dict[str, Any]
    attempts: int


@dataclass(frozen=True, slots=True)
class ClaimedSearchProjectionEvent:
    event: SearchProjectionEvent
    attempts: int


@dataclass(frozen=True, slots=True)
class SearchProjectionEventProcessResult:
    status: str
    event_id: UUID | None = None
    target: str | None = None
    indexed_count: int | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class SearchProjectionEventLoopResult:
    processed: int = 0
    failed: int = 0
    dead: int = 0
    empty: int = 0
    iterations: int = 0
    last_status: str | None = None


class SearchProjectionEventStore:
    """PostgreSQL durable queue for incremental OpenSearch projection jobs."""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    def enqueue(
        self,
        *,
        program_id: UUID | str,
        target: str,
        source_type: str,
        source_id: UUID | str | None = None,
        filters_json: Mapping[str, Any] | None = None,
        reset_existing: bool = False,
    ) -> UUID:
        target, source_type = validate_search_projection_event_contract(target=target, source_type=source_type)
        filters = normalize_target_filters(target=target, filters=filters_json or {})
        dedupe_key = _dedupe_key(
            program_id=program_id,
            target=target,
            source_type=source_type,
            source_id=source_id,
            filters=filters,
        )
        statement = _enqueue_statement(reset_existing=reset_existing)
        psycopg2, Json, RealDictCursor = _load_psycopg2()
        with psycopg2.connect(self.dsn) as connection:
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    statement,
                    (
                        uuid4(),
                        str(program_id),
                        target,
                        source_type,
                        None if source_id is None else str(source_id),
                        Json(filters),
                        dedupe_key,
                    ),
                )
                row = cursor.fetchone()
        if row is None:
            raise RuntimeError("search_projection_events insert did not return an id")
        return UUID(str(row["id"]))

    def enqueue_surface_component_outputs(
        self,
        *,
        program_id: UUID | str,
        analysis_run_id: UUID | str,
        snapshot_id: UUID | str,
        reset_existing: bool = False,
    ) -> tuple[UUID, UUID]:
        component_event_id = self.enqueue(
            program_id=program_id,
            target="surface-components",
            source_type=SEARCH_SURFACE_COMPONENTS_SOURCE,
            source_id=analysis_run_id,
            filters_json={"analysis_run_id": str(analysis_run_id)},
            reset_existing=reset_existing,
        )
        delta_event_id = self.enqueue(
            program_id=program_id,
            target="surface-deltas",
            source_type=SEARCH_SURFACE_DELTAS_SOURCE,
            source_id=snapshot_id,
            filters_json={"snapshot_id": str(snapshot_id)},
            reset_existing=reset_existing,
        )
        return component_event_id, delta_event_id

    def claim_next(
        self,
        *,
        worker_id: str,
        lock_seconds: int,
        max_attempts: int,
        program_id: UUID | str | None = None,
        target: str | None = None,
    ) -> ClaimedSearchProjectionEvent | None:
        target = validate_surface_projection_target(target)
        psycopg2, _Json, RealDictCursor = _load_psycopg2()
        now = datetime.now(UTC)
        locked_until = now + timedelta(seconds=lock_seconds)
        with psycopg2.connect(self.dsn) as connection:
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    """
WITH next_event AS (
    SELECT id
    FROM search_projection_events
    WHERE status IN ('pending', 'failed')
      AND available_at <= %(now)s
      AND attempts < %(max_attempts)s
      AND (%(program_id)s IS NULL OR program_id = %(program_id)s::uuid)
      AND (%(target)s IS NULL OR target = %(target)s)
      AND (locked_until IS NULL OR locked_until < %(now)s)
    ORDER BY available_at ASC, created_at ASC
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE search_projection_events
SET status = 'locked',
    locked_by = %(worker_id)s,
    locked_until = %(locked_until)s,
    attempts = attempts + 1,
    last_error = NULL,
    updated_at = %(now)s
WHERE id = (SELECT id FROM next_event)
RETURNING id,
          program_id,
          target,
          source_type,
          source_id,
          filters_json,
          attempts
""".strip(),
                    {
                        "worker_id": worker_id,
                        "now": now,
                        "locked_until": locked_until,
                        "max_attempts": max_attempts,
                        "program_id": None if program_id is None else str(program_id),
                        "target": target,
                    },
                )
                row = cursor.fetchone()
        if row is None:
            return None
        attempts = int(row["attempts"])
        event = SearchProjectionEvent(
            id=UUID(str(row["id"])),
            program_id=str(row["program_id"]),
            target=str(row["target"]),
            source_type=str(row["source_type"]),
            source_id=None if row.get("source_id") is None else str(row["source_id"]),
            filters_json=dict(row.get("filters_json") or {}),
            attempts=attempts,
        )
        return ClaimedSearchProjectionEvent(event=event, attempts=attempts)

    def mark_processed(self, event_id: UUID, *, indexed_count: int, worker_id: str) -> None:
        psycopg2, Json, _RealDictCursor = _load_psycopg2()
        now = datetime.now(UTC)
        with psycopg2.connect(self.dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
UPDATE search_projection_events
SET status = 'processed',
    processed_at = %s,
    updated_at = %s,
    locked_by = NULL,
    locked_until = NULL,
    last_error = NULL,
    result_json = %s
WHERE id = %s
  AND status = 'locked'
  AND locked_by = %s
""".strip(),
                    (now, now, Json({"indexed_count": indexed_count}), str(event_id), worker_id),
                )

    def mark_failed(self, event_id: UUID, *, error: str, dead: bool, worker_id: str) -> None:
        psycopg2, _Json, _RealDictCursor = _load_psycopg2()
        now = datetime.now(UTC)
        status = "dead" if dead else "failed"
        with psycopg2.connect(self.dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
UPDATE search_projection_events
SET status = %s,
    updated_at = %s,
    locked_by = NULL,
    locked_until = NULL,
    last_error = %s
WHERE id = %s
  AND status = 'locked'
  AND locked_by = %s
""".strip(),
                    (status, now, error[:4000], str(event_id), worker_id),
                )


class SearchProjectionEventWorker:
    def __init__(
        self,
        *,
        settings: Settings,
        event_store: SearchProjectionEventStore,
        worker_id: str,
        lock_seconds: int,
        max_attempts: int,
        limit: int,
        batch_size: int,
    ) -> None:
        self._settings = settings
        self._event_store = event_store
        self._worker_id = worker_id
        self._lock_seconds = lock_seconds
        self._max_attempts = max_attempts
        self._limit = limit
        self._batch_size = batch_size

    def process_one(
        self,
        *,
        program_id: UUID | str | None = None,
        target: str | None = None,
    ) -> SearchProjectionEventProcessResult:
        target = validate_surface_projection_target(target)
        claimed = self._event_store.claim_next(
            worker_id=self._worker_id,
            lock_seconds=self._lock_seconds,
            max_attempts=self._max_attempts,
            program_id=program_id,
            target=target,
        )
        if claimed is None:
            return SearchProjectionEventProcessResult(status="empty")
        event = claimed.event
        try:
            results = run_reindex(
                settings=self._settings,
                target=event.target,
                limit=self._limit,
                batch_size=self._batch_size,
                program_id=event.program_id,
                filters=event.filters_json,
            )
            indexed_count = int(results.get(event.target, 0))
        except Exception as exc:
            dead = claimed.attempts >= self._max_attempts
            status = "dead" if dead else "failed"
            error = str(exc)
            self._event_store.mark_failed(event.id, error=error, dead=dead, worker_id=self._worker_id)
            return SearchProjectionEventProcessResult(
                status=status,
                event_id=event.id,
                target=event.target,
                error=error,
            )
        self._event_store.mark_processed(event.id, indexed_count=indexed_count, worker_id=self._worker_id)
        return SearchProjectionEventProcessResult(
            status="processed",
            event_id=event.id,
            target=event.target,
            indexed_count=indexed_count,
        )

    def process_loop(
        self,
        *,
        program_id: UUID | str | None = None,
        target: str | None = None,
        max_events: int | None = None,
        idle_exit_after: int | None = None,
        poll_seconds: float = 1.0,
        sleep: Callable[[float], object] = default_sleep,
    ) -> SearchProjectionEventLoopResult:
        target = validate_surface_projection_target(target)
        if max_events is not None and max_events <= 0:
            raise ValueError("max_events must be positive when provided")
        if idle_exit_after is not None and idle_exit_after <= 0:
            raise ValueError("idle_exit_after must be positive when provided")
        if poll_seconds < 0:
            raise ValueError("poll_seconds must not be negative")

        processed = failed = dead = empty = iterations = 0
        consecutive_empty = 0
        last_status: str | None = None
        processed_events = 0
        while max_events is None or processed_events < max_events:
            result = self.process_one(program_id=program_id, target=target)
            iterations += 1
            last_status = result.status
            if result.status == "processed":
                processed += 1
                processed_events += 1
                consecutive_empty = 0
            elif result.status == "failed":
                failed += 1
                processed_events += 1
                consecutive_empty = 0
            elif result.status == "dead":
                dead += 1
                processed_events += 1
                consecutive_empty = 0
            elif result.status == "empty":
                empty += 1
                consecutive_empty += 1
                if idle_exit_after is not None and consecutive_empty >= idle_exit_after:
                    break
                if poll_seconds > 0:
                    sleep(poll_seconds)
            else:  # pragma: no cover
                raise RuntimeError(f"unknown search projection event status: {result.status}")
        return SearchProjectionEventLoopResult(
            processed=processed,
            failed=failed,
            dead=dead,
            empty=empty,
            iterations=iterations,
            last_status=last_status,
        )


def _dedupe_key(
    *,
    program_id: UUID | str,
    target: str,
    source_type: str,
    source_id: UUID | str | None,
    filters: Mapping[str, Any],
) -> str:
    filter_items = ",".join(f"{key}={filters[key]}" for key in sorted(filters))
    return f"search-projection:{program_id}:{target}:{source_type}:{source_id or 'none'}:{filter_items}"
