from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Callable, Mapping, Protocol
from uuid import UUID

from ..batch_store import GraphFactBatchStore
from ..contracts import GraphEdgeFact, GraphFactBatch, GraphNodeFact


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
        program_id = _required_uuid(row, "program_id")
        artifact_id = _required_uuid(row, "id")
        run_id = _optional_uuid(row.get("run_id"))
        if run_id is None:
            return None

        node_id = _required_text(row, "node_id")
        event_name = _required_text(row, "event_name")
        artifact_type = _required_text(row, "artifact_type")
        storage_uri = _required_text(row, "storage_uri")
        sha256 = _required_text(row, "sha256")
        size_bytes = int(row.get("size_bytes") or 0)
        job_id = _optional_uuid(row.get("job_id"))
        created_at = _optional_datetime(row.get("created_at"))
        producer = "raw-artifact-metadata"

        lineage = {
            "program_id": program_id,
            "producer": producer,
            "source_artifact_id": artifact_id,
            "tool_run_id": run_id,
            "confidence": 1.0,
        }

        facts = [
            GraphNodeFact(
                **lineage,
                kind="Program",
                key=str(program_id),
                properties={"program_id": str(program_id)},
            ),
            GraphNodeFact(
                **lineage,
                kind="Tool",
                key=node_id,
                properties={"tool_id": node_id, "event_name": event_name},
            ),
            GraphNodeFact(
                **lineage,
                kind="ToolRun",
                key=str(run_id),
                properties={
                    "tool_run_id": str(run_id),
                    "job_id": str(job_id) if job_id else None,
                    "node_id": node_id,
                    "event_name": event_name,
                },
            ),
            GraphNodeFact(
                **lineage,
                kind="Artifact",
                key=str(artifact_id),
                properties={
                    "artifact_id": str(artifact_id),
                    "artifact_type": artifact_type,
                    "storage_uri": storage_uri,
                    "sha256": sha256,
                    "size_bytes": size_bytes,
                    "node_id": node_id,
                    "event_name": event_name,
                    "created_at": created_at,
                },
            ),
            GraphEdgeFact(
                **lineage,
                src_kind="Program",
                src_key=str(program_id),
                edge_kind="HAS_TOOL_RUN",
                dst_kind="ToolRun",
                dst_key=str(run_id),
            ),
            GraphEdgeFact(
                **lineage,
                src_kind="ToolRun",
                src_key=str(run_id),
                edge_kind="USED_TOOL",
                dst_kind="Tool",
                dst_key=node_id,
            ),
            GraphEdgeFact(
                **lineage,
                src_kind="ToolRun",
                src_key=str(run_id),
                edge_kind="PRODUCED_ARTIFACT",
                dst_kind="Artifact",
                dst_key=str(artifact_id),
            ),
        ]

        return GraphFactBatch(
            program_id=program_id,
            produced_by=producer,
            parser_version=self._parser_version,
            facts=facts,
        )


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

    def enqueue_pending(self, *, limit: int = 100, program_id: UUID | str | None = None) -> RawArtifactEnqueueResult:
        if limit <= 0:
            raise ValueError("limit must be positive")

        rows = self._claim_rows(limit=limit, program_id=program_id)
        enqueued = 0
        skipped = 0
        for row in rows:
            event_id = _required_uuid(row, "projection_event_id")
            try:
                batch = self._producer.produce(row)
                if batch is None:
                    skipped += 1
                    self._mark_projection_event_processed(event_id)
                    continue
                artifact_id = _required_uuid(row, "id")
                self._store.enqueue(
                    batch,
                    dedupe_key=raw_artifact_dedupe_key(artifact_id, batch.parser_version),
                )
                self._mark_projection_event_processed(event_id)
                enqueued += 1
            except Exception as exc:
                attempts = int(row.get("projection_event_attempts") or 1)
                self._mark_projection_event_failed(
                    event_id,
                    error=str(exc),
                    dead=attempts >= self._max_attempts,
                )
                raise

        return RawArtifactEnqueueResult(scanned=len(rows), enqueued=enqueued, skipped=skipped)

    def _claim_rows(self, *, limit: int, program_id: UUID | str | None) -> list[Mapping[str, Any]]:
        now = datetime.now(UTC)
        locked_until = now + timedelta(seconds=self._lock_seconds)
        query = """
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

    def _mark_projection_event_processed(self, event_id: UUID) -> None:
        now = datetime.now(UTC)
        cursor = self._connection.cursor()
        cursor.execute(
            """
UPDATE graph_projection_events
SET status = 'processed',
    processed_at = %(now)s,
    updated_at = %(now)s,
    locked_by = NULL,
    locked_until = NULL,
    last_error = NULL
WHERE id = %(event_id)s;
""".strip(),
            {"event_id": event_id, "now": now},
        )
        if hasattr(self._connection, "commit"):
            self._connection.commit()

    def _mark_projection_event_failed(self, event_id: UUID, *, error: str, dead: bool) -> None:
        now = datetime.now(UTC)
        cursor = self._connection.cursor()
        cursor.execute(
            """
UPDATE graph_projection_events
SET status = %(status)s,
    updated_at = %(now)s,
    locked_by = NULL,
    locked_until = NULL,
    last_error = %(error)s
WHERE id = %(event_id)s;
""".strip(),
            {"event_id": event_id, "status": "dead" if dead else "failed", "now": now, "error": error[:4000]},
        )
        if hasattr(self._connection, "commit"):
            self._connection.commit()


def raw_artifact_dedupe_key(artifact_id: UUID | str, parser_version: str) -> str:
    return f"raw-artifact-metadata:{artifact_id}:{parser_version}"


def _required_uuid(row: Mapping[str, Any], key: str) -> UUID:
    value = _optional_uuid(row.get(key))
    if value is None:
        raise ValueError(f"raw artifact row requires {key}")
    return value


def _optional_uuid(value: Any) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


def _optional_uuid_text(value: UUID | str | None) -> str | None:
    if value is None:
        return None
    return str(_optional_uuid(value))


def _required_text(row: Mapping[str, Any], key: str) -> str:
    value = row.get(key)
    if value is None:
        raise ValueError(f"raw artifact row requires {key}")
    text = str(value).strip()
    if not text:
        raise ValueError(f"raw artifact row requires non-empty {key}")
    return text


def _optional_datetime(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    text = str(value).strip()
    return text or None
