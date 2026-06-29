from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Callable, Mapping, Protocol
from uuid import UUID

from ..batch_store import GraphFactBatchStore
from ..contracts import GraphFactBatch
from ..row_codec import optional_uuid_text as _optional_uuid_text, required_row_uuid
from .action_outcome_fact_builder import PRODUCER_NAME, build_action_outcome_graph_fact_batch
from .action_outcome_projection import action_outcome_projection_from_row, optional_datetime
from .projection_event_state import ProjectionEventStateWriter
from .raw_artifacts import default_sleep


class ActionOutcomeCursor(Protocol):
    def execute(self, query: str, parameters: dict[str, object] | None = None) -> object: ...
    def fetchall(self) -> list[Mapping[str, Any]]: ...


class ActionOutcomeConnection(Protocol):
    def cursor(self) -> ActionOutcomeCursor: ...


@dataclass(frozen=True)
class ActionOutcomeEnqueueResult:
    scanned: int = 0
    enqueued: int = 0
    skipped: int = 0


@dataclass(frozen=True)
class ActionOutcomeEnqueueLoopResult:
    scanned: int = 0
    enqueued: int = 0
    skipped: int = 0
    empty: int = 0
    iterations: int = 0

    @staticmethod
    def run(
        enqueuer: Any,
        *,
        limit: int,
        program_id: UUID | str | None = None,
        max_iterations: int | None = None,
        idle_exit_after: int | None = None,
        poll_seconds: float = 1.0,
        sleep: Callable[[float], object] = default_sleep,
    ) -> "ActionOutcomeEnqueueLoopResult":
        if limit <= 0:
            raise ValueError("limit must be positive")
        if max_iterations is not None and max_iterations <= 0:
            raise ValueError("max_iterations must be positive when provided")
        if idle_exit_after is not None and idle_exit_after <= 0:
            raise ValueError("idle_exit_after must be positive when provided")
        if poll_seconds < 0:
            raise ValueError("poll_seconds must not be negative")

        scanned = 0
        enqueued = 0
        skipped = 0
        empty = 0
        iterations = 0
        consecutive_empty = 0

        while max_iterations is None or iterations < max_iterations:
            result = enqueuer.enqueue_pending(limit=limit, program_id=program_id)
            iterations += 1
            scanned += result.scanned
            enqueued += result.enqueued
            skipped += result.skipped

            if result.scanned == 0:
                empty += 1
                consecutive_empty += 1
                if idle_exit_after is not None and consecutive_empty >= idle_exit_after:
                    break
                if poll_seconds > 0:
                    sleep(poll_seconds)
            else:
                consecutive_empty = 0

        return ActionOutcomeEnqueueLoopResult(
            scanned=scanned,
            enqueued=enqueued,
            skipped=skipped,
            empty=empty,
            iterations=iterations,
        )


class ActionOutcomeGraphFactProducer:
    """Project measured action outcomes into the Neo4j learning graph."""

    def __init__(self, *, parser_version: str = "action-outcome-memory.v1") -> None:
        self._parser_version = parser_version

    @property
    def parser_version(self) -> str:
        return self._parser_version

    def produce(self, row: Mapping[str, Any]) -> GraphFactBatch | None:
        projection = action_outcome_projection_from_row(row)
        return build_action_outcome_graph_fact_batch(projection, parser_version=self._parser_version)


class ActionOutcomeGraphFactEnqueuer:
    def __init__(
        self,
        *,
        connection: ActionOutcomeConnection,
        store: GraphFactBatchStore,
        producer: ActionOutcomeGraphFactProducer | None = None,
        worker_id: str = "graph-projector-action-outcome-enqueuer",
        lock_seconds: int = 300,
        max_attempts: int = 3,
    ) -> None:
        self._connection = connection
        self._store = store
        self._producer = producer or ActionOutcomeGraphFactProducer()
        self._worker_id = worker_id
        self._lock_seconds = lock_seconds
        self._max_attempts = max_attempts
        self._projection_events = ProjectionEventStateWriter(connection, worker_id=worker_id)

    def enqueue_pending(self, *, limit: int = 100, program_id: UUID | str | None = None) -> ActionOutcomeEnqueueResult:
        if limit <= 0:
            raise ValueError("limit must be positive")

        rows = self._claim_rows(limit=limit, program_id=program_id)
        enqueued = 0
        skipped = 0
        for row in rows:
            event_id = required_row_uuid(row, "projection_event_id", context="projection_event")
            try:
                batch = self._producer.produce(row)
                if batch is None:
                    skipped += 1
                    self._projection_events.mark_processed(event_id)
                    continue
                outcome_id = required_row_uuid(row, "id", context="action_outcome")
                self._store.enqueue(
                    batch,
                    dedupe_key=action_outcome_dedupe_key(outcome_id, row.get("updated_at"), batch.parser_version),
                    reset_existing=True,
                )
                self._projection_events.mark_processed(event_id)
                enqueued += 1
            except Exception as exc:
                attempts = int(row.get("projection_event_attempts") or 1)
                self._projection_events.mark_failed(
                    event_id,
                    error=str(exc),
                    dead=attempts >= self._max_attempts,
                )
                raise

        return ActionOutcomeEnqueueResult(scanned=len(rows), enqueued=enqueued, skipped=skipped)

    def _claim_rows(self, *, limit: int, program_id: UUID | str | None) -> list[Mapping[str, Any]]:
        now = datetime.now(UTC)
        locked_until = now + timedelta(seconds=self._lock_seconds)
        query = """
WITH next_events AS (
    SELECT id
    FROM graph_projection_events
    WHERE source_type = 'action_outcome'
      AND event_type IN ('action_outcome_recorded', 'action_outcome_updated')
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
    ao.*
FROM locked_events
JOIN action_outcomes ao ON ao.id = locked_events.source_id
ORDER BY locked_events.id ASC, ao.updated_at ASC;
""".strip()
        cursor = self._connection.cursor()
        cursor.execute(
            query,
            {
                "limit": limit,
                "program_id": _optional_uuid_text(program_id),
                "now": now,
                "locked_until": locked_until,
                "worker_id": self._worker_id,
                "max_attempts": self._max_attempts,
            },
        )
        rows = list(cursor.fetchall())
        if hasattr(self._connection, "commit"):
            self._connection.commit()
        return rows



def action_outcome_dedupe_key(outcome_id: UUID | str, updated_at: object, parser_version: str) -> str:
    timestamp = optional_datetime(updated_at)
    revision = timestamp.isoformat() if timestamp is not None else "unknown"
    return f"action-outcome:{outcome_id}:{revision}:{parser_version}"
