from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol
from uuid import UUID

from ..batch_store import GraphFactBatchStore
from ..contracts import GraphFactBatch
from ..row_codec import required_row_uuid
from .projection_event_state import ProjectionEventStateWriter
from .raw_artifact_claims import claim_raw_artifact_rows
from .raw_artifact_fact_builder import build_raw_artifact_batch
from .raw_artifact_keys import raw_artifact_dedupe_key


class RawArtifactCursor(Protocol):
    def execute(self, query: str, parameters: dict[str, object] | None = None) -> object: ...
    def fetchall(self) -> list[Mapping[str, Any]]: ...


class RawArtifactConnection(Protocol):
    def cursor(self) -> RawArtifactCursor: ...


@dataclass(frozen=True)
class RawArtifactEnqueueResult:
    scanned: int = 0
    enqueued: int = 0
    skipped: int = 0


def default_sleep(seconds: float) -> None:
    import time

    time.sleep(seconds)


@dataclass(frozen=True)
class RawArtifactEnqueueLoopResult:
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
    ) -> "RawArtifactEnqueueLoopResult":
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

        return RawArtifactEnqueueLoopResult(
            scanned=scanned,
            enqueued=enqueued,
            skipped=skipped,
            empty=empty,
            iterations=iterations,
        )


class RawArtifactGraphFactProducer:
    """Build L0 evidence-backbone GraphFacts from raw_artifacts metadata rows."""

    def __init__(self, *, parser_version: str = "raw-artifact-metadata.v1") -> None:
        self._parser_version = parser_version

    @property
    def parser_version(self) -> str:
        return self._parser_version

    def produce(self, row: Mapping[str, Any]) -> GraphFactBatch | None:
        return build_raw_artifact_batch(row, parser_version=self._parser_version)


class RawArtifactGraphFactEnqueuer:
    def __init__(
        self,
        *,
        connection: RawArtifactConnection,
        store: GraphFactBatchStore,
        producer: RawArtifactGraphFactProducer | None = None,
        worker_id: str = "graph-projector-raw-artifact-enqueuer",
        lock_seconds: int = 300,
        max_attempts: int = 3,
    ) -> None:
        self._connection = connection
        self._store = store
        self._producer = producer or RawArtifactGraphFactProducer()
        self._worker_id = worker_id
        self._lock_seconds = lock_seconds
        self._max_attempts = max_attempts
        self._projection_events = ProjectionEventStateWriter(connection, worker_id=worker_id)

    def enqueue_pending(self, *, limit: int = 100, program_id: UUID | str | None = None) -> RawArtifactEnqueueResult:
        if limit <= 0:
            raise ValueError("limit must be positive")

        rows = self._claim_rows(limit=limit, program_id=program_id)
        enqueued = 0
        skipped = 0
        for row in rows:
            event_id = required_row_uuid(row, "projection_event_id", context="raw artifact row")
            try:
                batch = self._producer.produce(row)
                if batch is None:
                    skipped += 1
                    self._projection_events.mark_processed(event_id)
                    continue
                artifact_id = required_row_uuid(row, "id", context="raw artifact row")
                self._store.enqueue(
                    batch,
                    dedupe_key=raw_artifact_dedupe_key(artifact_id, batch.parser_version),
                )
                self._projection_events.mark_processed(event_id)
                enqueued += 1
            except Exception as exc:
                attempts = int(row.get("projection_event_attempts") or 1)
                self._projection_events.mark_failed(
                    event_id,
                    error=str(exc),
                    dead=attempts >= self._max_attempts,
                    max_error_chars=4000,
                )
                raise

        return RawArtifactEnqueueResult(scanned=len(rows), enqueued=enqueued, skipped=skipped)

    def _claim_rows(self, *, limit: int, program_id: UUID | str | None) -> list[Mapping[str, Any]]:
        return claim_raw_artifact_rows(
            self._connection,
            limit=limit,
            program_id=program_id,
            worker_id=self._worker_id,
            lock_seconds=self._lock_seconds,
            max_attempts=self._max_attempts,
        )


__all__ = [
    "RawArtifactConnection",
    "RawArtifactCursor",
    "RawArtifactEnqueueLoopResult",
    "RawArtifactEnqueueResult",
    "RawArtifactGraphFactEnqueuer",
    "RawArtifactGraphFactProducer",
    "default_sleep",
    "raw_artifact_dedupe_key",
]
