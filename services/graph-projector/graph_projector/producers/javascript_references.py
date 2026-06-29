from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol
from uuid import UUID

from ..batch_store import GraphFactBatchStore
from ..contracts import GraphFactBatch
from ..row_codec import optional_uuid as _optional_uuid, required_row_uuid as _required_row_uuid
from .javascript_reference_claims import claim_javascript_reference_rows
from .javascript_reference_fact_builder import build_javascript_reference_graph_fact_batch
from .javascript_reference_keys import (
    canonical_url_without_query as _canonical_url_without_query,
    javascript_reference_dedupe_key,
    js_file_key,
)
from .projection_event_state import ProjectionEventStateWriter
from .raw_artifacts import default_sleep


class JavaScriptReferenceCursor(Protocol):
    def execute(self, query: str, parameters: dict[str, object] | None = None) -> object: ...
    def fetchall(self) -> list[Mapping[str, Any]]: ...


class JavaScriptReferenceConnection(Protocol):
    def cursor(self) -> JavaScriptReferenceCursor: ...


@dataclass(frozen=True)
class JavaScriptReferenceEnqueueResult:
    scanned: int = 0
    enqueued: int = 0
    skipped: int = 0


@dataclass(frozen=True)
class JavaScriptReferenceEnqueueLoopResult:
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
    ) -> "JavaScriptReferenceEnqueueLoopResult":
        _validate_loop_inputs(
            limit=limit,
            max_iterations=max_iterations,
            idle_exit_after=idle_exit_after,
            poll_seconds=poll_seconds,
        )
        return _run_enqueue_loop(
            enqueuer,
            limit=limit,
            program_id=program_id,
            max_iterations=max_iterations,
            idle_exit_after=idle_exit_after,
            poll_seconds=poll_seconds,
            sleep=sleep,
        )


class JavaScriptReferenceGraphFactProducer:
    def __init__(self, *, parser_version: str = "javascript-references.v1") -> None:
        self._parser_version = parser_version

    @property
    def parser_version(self) -> str:
        return self._parser_version

    def produce(self, rows: list[Mapping[str, Any]]) -> GraphFactBatch | None:
        return build_javascript_reference_graph_fact_batch(rows, parser_version=self._parser_version)


class JavaScriptReferenceGraphFactEnqueuer:
    def __init__(
        self,
        connection: JavaScriptReferenceConnection,
        store: GraphFactBatchStore,
        producer: JavaScriptReferenceGraphFactProducer | None = None,
        worker_id: str = "graph-projector-javascript-reference-enqueuer",
        lock_seconds: int = 300,
        max_attempts: int = 3,
    ) -> None:
        self._connection = connection
        self._store = store
        self._producer = producer or JavaScriptReferenceGraphFactProducer()
        self._worker_id = worker_id
        self._lock_seconds = lock_seconds
        self._max_attempts = max_attempts
        self._projection_events = ProjectionEventStateWriter(connection, worker_id=worker_id)

    def enqueue_pending(self, *, limit: int = 100, program_id: UUID | str | None = None) -> JavaScriptReferenceEnqueueResult:
        if limit <= 0:
            raise ValueError("limit must be positive")

        grouped_rows = _group_rows_by_projection_event(self._claim_rows(limit=limit, program_id=program_id))
        enqueued = 0
        skipped = 0
        for event_id, event_rows in grouped_rows.items():
            try:
                if self._enqueue_event_rows(event_id, event_rows):
                    enqueued += 1
                else:
                    skipped += 1
            except Exception as exc:
                self._mark_event_failed(event_id, event_rows, exc)
                raise

        return JavaScriptReferenceEnqueueResult(scanned=len(grouped_rows), enqueued=enqueued, skipped=skipped)

    def _claim_rows(self, *, limit: int, program_id: UUID | str | None) -> list[Mapping[str, Any]]:
        return claim_javascript_reference_rows(
            self._connection,
            limit=limit,
            program_id=program_id,
            worker_id=self._worker_id,
            lock_seconds=self._lock_seconds,
            max_attempts=self._max_attempts,
        )

    def _enqueue_event_rows(self, event_id: UUID, event_rows: list[Mapping[str, Any]]) -> bool:
        batch = self._producer.produce(event_rows)
        if batch is None:
            self._projection_events.mark_processed(event_id)
            return False

        self._store.enqueue(
            batch,
            dedupe_key=javascript_reference_dedupe_key(_first_required_raw_artifact_id(event_rows), batch.parser_version),
        )
        self._projection_events.mark_processed(event_id)
        return True

    def _mark_event_failed(self, event_id: UUID, event_rows: list[Mapping[str, Any]], exc: Exception) -> None:
        attempts = int(event_rows[0].get("projection_event_attempts") or 1)
        self._projection_events.mark_failed(
            event_id,
            error=str(exc),
            dead=attempts >= self._max_attempts,
            max_error_chars=4000,
        )


def _validate_loop_inputs(
    *,
    limit: int,
    max_iterations: int | None,
    idle_exit_after: int | None,
    poll_seconds: float,
) -> None:
    if limit <= 0:
        raise ValueError("limit must be positive")
    if max_iterations is not None and max_iterations <= 0:
        raise ValueError("max_iterations must be positive when provided")
    if idle_exit_after is not None and idle_exit_after <= 0:
        raise ValueError("idle_exit_after must be positive when provided")
    if poll_seconds < 0:
        raise ValueError("poll_seconds must not be negative")


def _run_enqueue_loop(
    enqueuer: Any,
    *,
    limit: int,
    program_id: UUID | str | None,
    max_iterations: int | None,
    idle_exit_after: int | None,
    poll_seconds: float,
    sleep: Callable[[float], object],
) -> JavaScriptReferenceEnqueueLoopResult:
    state = _LoopState()
    while max_iterations is None or state.iterations < max_iterations:
        result = enqueuer.enqueue_pending(limit=limit, program_id=program_id)
        state.record(result)
        if state.should_stop_after(result, idle_exit_after=idle_exit_after):
            break
        if result.scanned == 0 and poll_seconds > 0:
            sleep(poll_seconds)
    return state.result()


@dataclass
class _LoopState:
    scanned: int = 0
    enqueued: int = 0
    skipped: int = 0
    empty: int = 0
    iterations: int = 0
    consecutive_empty: int = 0

    def record(self, result: JavaScriptReferenceEnqueueResult) -> None:
        self.iterations += 1
        self.scanned += result.scanned
        self.enqueued += result.enqueued
        self.skipped += result.skipped
        if result.scanned == 0:
            self.empty += 1
            self.consecutive_empty += 1
        else:
            self.consecutive_empty = 0

    def should_stop_after(self, result: JavaScriptReferenceEnqueueResult, *, idle_exit_after: int | None) -> bool:
        return result.scanned == 0 and idle_exit_after is not None and self.consecutive_empty >= idle_exit_after

    def result(self) -> JavaScriptReferenceEnqueueLoopResult:
        return JavaScriptReferenceEnqueueLoopResult(
            scanned=self.scanned,
            enqueued=self.enqueued,
            skipped=self.skipped,
            empty=self.empty,
            iterations=self.iterations,
        )


def _group_rows_by_projection_event(rows: list[Mapping[str, Any]]) -> "OrderedDict[UUID, list[Mapping[str, Any]]]":
    grouped: "OrderedDict[UUID, list[Mapping[str, Any]]]" = OrderedDict()
    for row in rows:
        event_id = _required_row_uuid(row, "projection_event_id", context="javascript reference projection event row")
        grouped.setdefault(event_id, []).append(row)
    return grouped


def _first_required_raw_artifact_id(rows: list[Mapping[str, Any]]) -> UUID:
    for row in rows:
        value = _optional_uuid(row.get("raw_artifact_id"))
        if value is not None:
            return value
    raise ValueError("javascript reference batch requires raw_artifact_id")
