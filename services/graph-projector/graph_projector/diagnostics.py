from __future__ import annotations

from dataclasses import dataclass
import shlex
from typing import Any, Mapping, Protocol
from uuid import UUID

from .health import GraphProjectorHealthCheck, GraphProjectorHealthChecker, GraphProjectorHealthThresholds
from .row_codec import fetchall as _fetchall_rows, optional_uuid_text as _optional_uuid_text
from .status import GraphProjectorStatusReader


class DiagnosticsCursor(Protocol):
    def execute(self, query: str, parameters: dict[str, object] | None = None) -> object: ...
    def fetchall(self) -> list[Mapping[str, Any]]: ...


class DiagnosticsConnection(Protocol):
    def cursor(self) -> DiagnosticsCursor: ...


@dataclass(frozen=True)
class ProjectionEventDiagnosticSample:
    id: str
    program_id: str
    source_type: str
    source_id: str
    event_type: str
    status: str
    attempts: int
    last_error: str | None
    updated_at: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "program_id": self.program_id,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "event_type": self.event_type,
            "status": self.status,
            "attempts": self.attempts,
            "last_error": self.last_error,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class GraphFactBatchDiagnosticSample:
    id: str
    program_id: str
    produced_by: str
    parser_version: str
    status: str
    attempts: int
    fact_count: int
    last_error: str | None
    updated_at: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "program_id": self.program_id,
            "produced_by": self.produced_by,
            "parser_version": self.parser_version,
            "status": self.status,
            "attempts": self.attempts,
            "fact_count": self.fact_count,
            "last_error": self.last_error,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class SurfaceAnalysisEventDiagnosticSample:
    id: str
    program_id: str
    snapshot_id: str
    previous_snapshot_id: str | None
    event_type: str
    analysis_version: str
    status: str
    attempts: int
    last_error: str | None
    updated_at: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "program_id": self.program_id,
            "snapshot_id": self.snapshot_id,
            "previous_snapshot_id": self.previous_snapshot_id,
            "event_type": self.event_type,
            "analysis_version": self.analysis_version,
            "status": self.status,
            "attempts": self.attempts,
            "last_error": self.last_error,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class GraphProjectorDiagnosticsReport:
    health: GraphProjectorHealthCheck
    projection_event_samples: tuple[ProjectionEventDiagnosticSample, ...]
    graph_fact_batch_samples: tuple[GraphFactBatchDiagnosticSample, ...]
    surface_analysis_event_samples: tuple[SurfaceAnalysisEventDiagnosticSample, ...]
    rebuild_sources: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "health": self.health.to_dict(),
            "rebuild_sources": list(self.rebuild_sources),
            "projection_event_samples": [sample.to_dict() for sample in self.projection_event_samples],
            "graph_fact_batch_samples": [sample.to_dict() for sample in self.graph_fact_batch_samples],
            "surface_analysis_event_samples": [sample.to_dict() for sample in self.surface_analysis_event_samples],
            "suggested_commands": self.suggested_commands(),
        }

    def suggested_commands(self) -> list[str]:
        commands: list[str] = []
        metrics = self.health.metrics
        if metrics.get("projection_events_failed", 0) or metrics.get("projection_events_dead", 0):
            commands.append(_graph_projector_command("retry", "--queue", "projection_events"))
        if metrics.get("graph_fact_batches_failed", 0) or metrics.get("graph_fact_batches_dead", 0):
            commands.append(_graph_projector_command("retry", "--queue", "graph_fact_batches"))
        if metrics.get("projection_events_pending", 0):
            commands.append(_graph_projector_command("process-projection-events"))
        if metrics.get("graph_fact_batches_pending", 0):
            commands.append(_graph_projector_command("apply-one"))
        if metrics.get("surface_analysis_events_failed", 0) or metrics.get("surface_analysis_events_dead", 0):
            commands.append(_graph_projector_command("retry", "--queue", "surface_analysis_events"))
        if metrics.get("surface_analysis_events_pending", 0):
            commands.append(_graph_projector_command("process-surface-analysis-events"))
        return commands


def _graph_projector_command(*args: object) -> str:
    return shlex.join(["python", "-m", "graph_projector", *(str(arg) for arg in args)])


class GraphProjectorDiagnosticsReader:
    """Read a machine-readable operational snapshot for graph projection.

    Diagnostics is read-only. It combines durable queue health with bounded
    failed/dead samples so CI/ops can decide whether to retry, process, apply,
    or selectively rebuild without mutating PostgreSQL or Neo4j.
    """

    def __init__(self, connection: DiagnosticsConnection) -> None:
        self._connection = connection
        self._status_reader = GraphProjectorStatusReader(connection)
        self._health_checker = GraphProjectorHealthChecker(self._status_reader)

    def read(
        self,
        *,
        program_id: UUID | str | None = None,
        thresholds: GraphProjectorHealthThresholds | None = None,
        sample_limit: int = 5,
    ) -> GraphProjectorDiagnosticsReport:
        if sample_limit < 0:
            raise ValueError("sample_limit must be non-negative")
        health = self._health_checker.check(program_id=program_id, thresholds=thresholds)
        status_report = self._status_reader.read(program_id=program_id)
        return GraphProjectorDiagnosticsReport(
            health=health,
            projection_event_samples=self._projection_event_samples(program_id=program_id, limit=sample_limit),
            graph_fact_batch_samples=self._graph_fact_batch_samples(program_id=program_id, limit=sample_limit),
            surface_analysis_event_samples=self._surface_analysis_event_samples(program_id=program_id, limit=sample_limit),
            rebuild_sources=status_report.rebuild_sources,
        )

    def _projection_event_samples(
        self,
        *,
        program_id: UUID | str | None,
        limit: int,
    ) -> tuple[ProjectionEventDiagnosticSample, ...]:
        if limit == 0:
            return ()
        rows = self._fetchall(
            """
SELECT id,
       program_id,
       source_type,
       source_id,
       event_type,
       status,
       attempts,
       last_error,
       updated_at
FROM graph_projection_events
WHERE status IN ('failed', 'dead')
  AND (%(program_id)s IS NULL OR program_id = %(program_id)s)
ORDER BY updated_at DESC, created_at DESC
LIMIT %(limit)s;
""".strip(),
            {"program_id": _optional_uuid_text(program_id), "limit": limit},
        )
        return tuple(
            ProjectionEventDiagnosticSample(
                id=str(row["id"]),
                program_id=str(row["program_id"]),
                source_type=str(row["source_type"]),
                source_id=str(row["source_id"]),
                event_type=str(row["event_type"]),
                status=str(row["status"]),
                attempts=int(row["attempts"]),
                last_error=None if row.get("last_error") is None else str(row["last_error"]),
                updated_at=None if row.get("updated_at") is None else str(row["updated_at"]),
            )
            for row in rows
        )

    def _graph_fact_batch_samples(
        self,
        *,
        program_id: UUID | str | None,
        limit: int,
    ) -> tuple[GraphFactBatchDiagnosticSample, ...]:
        if limit == 0:
            return ()
        rows = self._fetchall(
            """
SELECT id,
       program_id,
       produced_by,
       parser_version,
       status,
       attempts,
       fact_count,
       last_error,
       updated_at
FROM graph_fact_batches
WHERE status IN ('failed', 'dead')
  AND (%(program_id)s IS NULL OR program_id = %(program_id)s)
ORDER BY updated_at DESC, created_at DESC
LIMIT %(limit)s;
""".strip(),
            {"program_id": _optional_uuid_text(program_id), "limit": limit},
        )
        return tuple(
            GraphFactBatchDiagnosticSample(
                id=str(row["id"]),
                program_id=str(row["program_id"]),
                produced_by=str(row["produced_by"]),
                parser_version=str(row["parser_version"]),
                status=str(row["status"]),
                attempts=int(row["attempts"]),
                fact_count=int(row["fact_count"]),
                last_error=None if row.get("last_error") is None else str(row["last_error"]),
                updated_at=None if row.get("updated_at") is None else str(row["updated_at"]),
            )
            for row in rows
        )

    def _surface_analysis_event_samples(
        self,
        *,
        program_id: UUID | str | None,
        limit: int,
    ) -> tuple[SurfaceAnalysisEventDiagnosticSample, ...]:
        if limit == 0:
            return ()
        rows = self._fetchall(
            """
SELECT id,
       program_id,
       snapshot_id,
       previous_snapshot_id,
       event_type,
       analysis_version,
       status,
       attempts,
       last_error,
       updated_at
FROM surface_component_analysis_events
WHERE status IN ('failed', 'dead')
  AND (%(program_id)s IS NULL OR program_id = %(program_id)s)
ORDER BY updated_at DESC, created_at DESC
LIMIT %(limit)s;
""".strip(),
            {"program_id": _optional_uuid_text(program_id), "limit": limit},
        )
        return tuple(
            SurfaceAnalysisEventDiagnosticSample(
                id=str(row["id"]),
                program_id=str(row["program_id"]),
                snapshot_id=str(row["snapshot_id"]),
                previous_snapshot_id=None if row.get("previous_snapshot_id") is None else str(row["previous_snapshot_id"]),
                event_type=str(row["event_type"]),
                analysis_version=str(row["analysis_version"]),
                status=str(row["status"]),
                attempts=int(row["attempts"]),
                last_error=None if row.get("last_error") is None else str(row["last_error"]),
                updated_at=None if row.get("updated_at") is None else str(row["updated_at"]),
            )
            for row in rows
        )

    def _fetchall(self, query: str, parameters: dict[str, object]) -> list[Mapping[str, Any]]:
        return _fetchall_rows(self._connection, query, parameters)
