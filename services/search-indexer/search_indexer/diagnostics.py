"""Read-only diagnostics for OpenSearch projection events."""
from __future__ import annotations

from dataclasses import dataclass
import shlex
from typing import Any, Mapping, Protocol
from uuid import UUID

from .health import SearchIndexerHealthCheck, SearchIndexerHealthChecker, SearchIndexerHealthThresholds
from .status import SearchIndexerStatusReader


class DiagnosticsCursor(Protocol):
    def execute(self, query: str, parameters: dict[str, object] | None = None) -> object: ...
    def fetchall(self) -> list[Mapping[str, Any]]: ...


class DiagnosticsConnection(Protocol):
    def cursor(self) -> DiagnosticsCursor: ...


@dataclass(frozen=True)
class SearchProjectionEventDiagnosticSample:
    id: str
    program_id: str
    target: str
    source_type: str
    source_id: str | None
    status: str
    attempts: int
    last_error: str | None
    updated_at: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "program_id": self.program_id,
            "target": self.target,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "status": self.status,
            "attempts": self.attempts,
            "last_error": self.last_error,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class SearchIndexerDiagnosticsReport:
    health: SearchIndexerHealthCheck
    event_samples: tuple[SearchProjectionEventDiagnosticSample, ...]
    reindex_targets: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "health": self.health.to_dict(),
            "reindex_targets": list(self.reindex_targets),
            "event_samples": [sample.to_dict() for sample in self.event_samples],
            "suggested_commands": self.suggested_commands(),
        }

    def suggested_commands(self) -> list[str]:
        commands: list[str] = []
        metrics = self.health.metrics
        if metrics.get("search_projection_events_failed", 0) or metrics.get("search_projection_events_dead", 0):
            commands.append(_search_indexer_command("retry"))
        if metrics.get("search_projection_events_pending", 0):
            commands.append(_search_indexer_command("process-events"))
        return commands


def _search_indexer_command(*args: object) -> str:
    return shlex.join(["python", "-m", "search_indexer", *(str(arg) for arg in args)])


class SearchIndexerDiagnosticsReader:
    """Combine queue health with bounded failed/dead samples.

    Diagnostics is read-only. It does not call OpenSearch, reindex, retry, or
    enqueue projection events.
    """

    def __init__(self, connection: DiagnosticsConnection) -> None:
        self._connection = connection
        self._status_reader = SearchIndexerStatusReader(connection)
        self._health_checker = SearchIndexerHealthChecker(self._status_reader)

    def read(
        self,
        *,
        program_id: UUID | str | None = None,
        target: str | None = None,
        thresholds: SearchIndexerHealthThresholds | None = None,
        sample_limit: int = 5,
    ) -> SearchIndexerDiagnosticsReport:
        if sample_limit < 0:
            raise ValueError("sample_limit must be non-negative")
        health = self._health_checker.check(program_id=program_id, target=target, thresholds=thresholds)
        status_report = self._status_reader.read(program_id=program_id, target=target)
        return SearchIndexerDiagnosticsReport(
            health=health,
            event_samples=self._event_samples(program_id=program_id, target=target, limit=sample_limit),
            reindex_targets=status_report.reindex_targets,
        )

    def _event_samples(
        self,
        *,
        program_id: UUID | str | None,
        target: str | None,
        limit: int,
    ) -> tuple[SearchProjectionEventDiagnosticSample, ...]:
        if limit == 0:
            return ()
        rows = self._fetchall(
            """
SELECT id,
       program_id,
       target,
       source_type,
       source_id,
       status,
       attempts,
       last_error,
       updated_at
FROM search_projection_events
WHERE status IN ('failed', 'dead')
  AND (%(program_id)s IS NULL OR program_id = %(program_id)s::uuid)
  AND (%(target)s IS NULL OR target = %(target)s)
ORDER BY updated_at DESC, created_at DESC
LIMIT %(limit)s;
""".strip(),
            {
                "program_id": None if program_id is None else str(program_id),
                "target": target,
                "limit": limit,
            },
        )
        return tuple(
            SearchProjectionEventDiagnosticSample(
                id=str(row["id"]),
                program_id=str(row["program_id"]),
                target=str(row["target"]),
                source_type=str(row["source_type"]),
                source_id=None if row.get("source_id") is None else str(row["source_id"]),
                status=str(row["status"]),
                attempts=int(row["attempts"]),
                last_error=None if row.get("last_error") is None else str(row["last_error"]),
                updated_at=None if row.get("updated_at") is None else str(row["updated_at"]),
            )
            for row in rows
        )

    def _fetchall(self, query: str, parameters: dict[str, object]) -> list[Mapping[str, Any]]:
        cursor = self._cursor()
        cursor.execute(query, parameters)
        return list(cursor.fetchall())

    def _cursor(self) -> DiagnosticsCursor:
        cursor = self._connection.cursor()
        if hasattr(cursor, "__enter__"):
            return cursor.__enter__()
        return cursor
