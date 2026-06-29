from __future__ import annotations

import select
from dataclasses import dataclass
from time import sleep as default_sleep
from typing import Any, Callable, Protocol
from uuid import UUID

from .notify_channels import listen_statement, validate_postgres_notify_channel


class ProjectionEventEnqueuer(Protocol):
    def enqueue_pending(self, *, limit: int, program_id: UUID | str | None = None) -> Any: ...


class GraphProjectionEventNotificationWaiter:
    """Wait for PostgreSQL NOTIFY; durable state remains graph_projection_events."""

    def __init__(self, connection: Any, *, channel: str = "graph_projection_events_changed") -> None:
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
class ProjectionEventWorkerResult:
    scanned: int = 0
    enqueued: int = 0
    skipped: int = 0
    empty: int = 0
    iterations: int = 0


class GraphProjectionEventWorker:
    def __init__(
        self,
        *,
        raw_artifact_enqueuer: ProjectionEventEnqueuer,
        http_observation_enqueuer: ProjectionEventEnqueuer,
        javascript_reference_enqueuer: ProjectionEventEnqueuer,
        action_outcome_enqueuer: ProjectionEventEnqueuer | None = None,
    ) -> None:
        enqueuers: list[ProjectionEventEnqueuer] = [
            raw_artifact_enqueuer,
            http_observation_enqueuer,
            javascript_reference_enqueuer,
        ]
        if action_outcome_enqueuer is not None:
            enqueuers.append(action_outcome_enqueuer)
        self._enqueuers = tuple(enqueuers)

    def process_once(self, *, limit: int = 100, program_id: UUID | str | None = None) -> ProjectionEventWorkerResult:
        if limit <= 0:
            raise ValueError("limit must be positive")

        scanned = 0
        enqueued = 0
        skipped = 0
        for enqueuer in self._enqueuers:
            result = enqueuer.enqueue_pending(limit=limit, program_id=program_id)
            scanned += int(getattr(result, "scanned", 0))
            enqueued += int(getattr(result, "enqueued", 0))
            skipped += int(getattr(result, "skipped", 0))

        return ProjectionEventWorkerResult(scanned=scanned, enqueued=enqueued, skipped=skipped)

    def process_loop(
        self,
        *,
        limit: int = 100,
        program_id: UUID | str | None = None,
        max_iterations: int | None = None,
        idle_exit_after: int | None = None,
        poll_seconds: float = 1.0,
        sleep: Callable[[float], object] = default_sleep,
        wait_for_notification: Callable[[float], object] | None = None,
    ) -> ProjectionEventWorkerResult:
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
            result = self.process_once(limit=limit, program_id=program_id)
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
                    if wait_for_notification is not None:
                        wait_for_notification(poll_seconds)
                    else:
                        sleep(poll_seconds)
            else:
                consecutive_empty = 0

        return ProjectionEventWorkerResult(
            scanned=scanned,
            enqueued=enqueued,
            skipped=skipped,
            empty=empty,
            iterations=iterations,
        )


def _safe_postgres_identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError(f"unsafe PostgreSQL identifier: {value}")
    return value
