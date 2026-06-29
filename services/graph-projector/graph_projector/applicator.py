from __future__ import annotations

import select
from dataclasses import dataclass
from time import sleep as default_sleep
from typing import Any, Callable, Protocol
from uuid import UUID

from .batch_store import GraphFactBatchStore
from .notify_channels import listen_statement, validate_postgres_notify_channel
from .writer import GraphFactWriteResult, GraphFactWriter


class Neo4jDriver(Protocol):
    def session(self, *, database: str): ...


class GraphFactBatchNotificationWaiter:
    """Wait for PostgreSQL NOTIFY when GraphFactBatch rows become available.

    The durable source is still `graph_fact_batches`; NOTIFY only wakes the
    apply loop sooner than the periodic fallback poll.
    """

    def __init__(self, connection: Any, *, channel: str = "graph_fact_batches_changed") -> None:
        self._connection = connection
        self._channel = validate_postgres_notify_channel(channel)
        self._listening = False

    def wait(self, timeout_seconds: float) -> None:
        if timeout_seconds < 0:
            raise ValueError("timeout_seconds must not be negative")
        self._ensure_listening()
        ready, _, _ = select.select([self._connection], [], [], timeout_seconds)
        if ready and hasattr(self._connection, "poll"):
            self._connection.poll()
        notifies = getattr(self._connection, "notifies", None)
        if notifies is not None:
            notifies.clear()

    def _ensure_listening(self) -> None:
        if self._listening:
            return
        if hasattr(self._connection, "autocommit"):
            self._connection.autocommit = True
        cursor = self._connection.cursor()
        cursor.execute(listen_statement(self._channel))
        if hasattr(self._connection, "commit"):
            self._connection.commit()
        self._listening = True


@dataclass(frozen=True)
class GraphFactBatchApplyResult:
    status: str
    batch_id: UUID | None = None
    write_result: GraphFactWriteResult | None = None
    error: str | None = None


@dataclass(frozen=True)
class GraphFactBatchLoopResult:
    applied: int = 0
    failed: int = 0
    dead: int = 0
    empty: int = 0
    iterations: int = 0
    last_status: str | None = None


class GraphFactBatchApplicator:
    def __init__(
        self,
        *,
        store: GraphFactBatchStore,
        neo4j_driver: Neo4jDriver,
        writer: GraphFactWriter,
        neo4j_database: str,
        worker_id: str,
        lock_seconds: int,
        max_attempts: int,
        after_apply: Callable[[Any], object] | None = None,
    ) -> None:
        self._store = store
        self._neo4j_driver = neo4j_driver
        self._writer = writer
        self._neo4j_database = neo4j_database
        self._worker_id = worker_id
        self._lock_seconds = lock_seconds
        self._max_attempts = max_attempts
        self._after_apply = after_apply

    def apply_one(self) -> GraphFactBatchApplyResult:
        claimed = self._store.claim_next(
            worker_id=self._worker_id,
            lock_seconds=self._lock_seconds,
            max_attempts=self._max_attempts,
        )
        if claimed is None:
            return GraphFactBatchApplyResult(status="empty")

        try:
            with self._neo4j_driver.session(database=self._neo4j_database) as session:
                write_result = self._writer.write_batch(session, claimed.batch)
        except Exception as exc:
            dead = claimed.attempts >= self._max_attempts
            status = "dead" if dead else "failed"
            error = str(exc)
            self._store.mark_failed(claimed.batch_id, error=error, dead=dead, worker_id=self._worker_id)
            return GraphFactBatchApplyResult(status=status, batch_id=claimed.batch_id, error=error)

        if write_result.edges_skipped > 0:
            dead = claimed.attempts >= self._max_attempts
            status = "dead" if dead else "failed"
            error = _skipped_edges_error(write_result.edges_skipped)
            self._store.mark_failed(claimed.batch_id, error=error, dead=dead, worker_id=self._worker_id)
            return GraphFactBatchApplyResult(
                status=status,
                batch_id=claimed.batch_id,
                write_result=write_result,
                error=error,
            )

        if self._after_apply is not None:
            try:
                self._after_apply(claimed.batch)
            except Exception as exc:
                dead = claimed.attempts >= self._max_attempts
                status = "dead" if dead else "failed"
                error = str(exc)
                self._store.mark_failed(claimed.batch_id, error=error, dead=dead, worker_id=self._worker_id)
                return GraphFactBatchApplyResult(
                    status=status,
                    batch_id=claimed.batch_id,
                    write_result=write_result,
                    error=error,
                )

        self._store.mark_applied(claimed.batch_id, worker_id=self._worker_id)
        return GraphFactBatchApplyResult(
            status="applied",
            batch_id=claimed.batch_id,
            write_result=write_result,
        )

    def apply_loop(
        self,
        *,
        max_batches: int | None = None,
        idle_exit_after: int | None = None,
        poll_seconds: float = 1.0,
        sleep: Callable[[float], object] = default_sleep,
        wait_for_notification: Callable[[float], object] | None = None,
    ) -> GraphFactBatchLoopResult:
        if max_batches is not None and max_batches <= 0:
            raise ValueError("max_batches must be positive when provided")
        if idle_exit_after is not None and idle_exit_after <= 0:
            raise ValueError("idle_exit_after must be positive when provided")
        if poll_seconds < 0:
            raise ValueError("poll_seconds must not be negative")

        applied = 0
        failed = 0
        dead = 0
        empty = 0
        iterations = 0
        processed_batches = 0
        consecutive_empty = 0
        last_status: str | None = None

        while max_batches is None or iterations < max_batches:
            result = self.apply_one()
            iterations += 1
            last_status = result.status

            if result.status == "applied":
                applied += 1
                processed_batches += 1
                consecutive_empty = 0
            elif result.status == "failed":
                failed += 1
                processed_batches += 1
                consecutive_empty = 0
            elif result.status == "dead":
                dead += 1
                processed_batches += 1
                consecutive_empty = 0
            elif result.status == "empty":
                empty += 1
                consecutive_empty += 1
                if idle_exit_after is not None and consecutive_empty >= idle_exit_after:
                    break
                if poll_seconds > 0:
                    if wait_for_notification is not None:
                        wait_for_notification(poll_seconds)
                    else:
                        sleep(poll_seconds)
            else:  # pragma: no cover - defensive guard for future statuses
                raise RuntimeError(f"unknown graphfact apply status: {result.status}")

            if max_batches is not None and processed_batches >= max_batches:
                break

        return GraphFactBatchLoopResult(
            applied=applied,
            failed=failed,
            dead=dead,
            empty=empty,
            iterations=iterations,
            last_status=last_status,
        )


def _safe_postgres_identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError(f"unsafe PostgreSQL identifier: {value}")
    return value


def _skipped_edges_error(edges_skipped: int) -> str:
    return f"GraphFactBatch skipped {edges_skipped} edge(s); missing endpoint nodes may arrive later"
