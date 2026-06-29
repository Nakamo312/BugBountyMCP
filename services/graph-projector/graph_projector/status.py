from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol
from uuid import UUID

from .rebuild import GRAPH_REBUILD_SOURCES
from .row_codec import fetchall as _fetchall_rows


class StatusCursor(Protocol):
    def execute(self, query: str, parameters: dict[str, object] | None = None) -> object: ...
    def fetchall(self) -> list[Mapping[str, Any]]: ...


class StatusConnection(Protocol):
    def cursor(self) -> StatusCursor: ...


@dataclass(frozen=True)
class ProjectionEventStatusCount:
    source_type: str
    event_type: str
    status: str
    count: int


@dataclass(frozen=True)
class SurfaceComponentAnalysisEventStatusCount:
    event_type: str
    status: str
    count: int


@dataclass(frozen=True)
class GraphFactBatchStatusCount:
    parser_version: str
    status: str
    count: int


@dataclass(frozen=True)
class GraphProjectorStatusReport:
    projection_events: tuple[ProjectionEventStatusCount, ...]
    graph_fact_batches: tuple[GraphFactBatchStatusCount, ...]
    surface_analysis_events: tuple[SurfaceComponentAnalysisEventStatusCount, ...]
    rebuild_sources: tuple[str, ...]

    @property
    def pending_projection_events(self) -> int:
        return _sum_status(self.projection_events, "pending")

    @property
    def failed_projection_events(self) -> int:
        return _sum_status(self.projection_events, "failed")

    @property
    def dead_projection_events(self) -> int:
        return _sum_status(self.projection_events, "dead")

    @property
    def pending_graph_fact_batches(self) -> int:
        return _sum_status(self.graph_fact_batches, "pending")

    @property
    def pending_surface_analysis_events(self) -> int:
        return _sum_status(self.surface_analysis_events, "pending")

    @property
    def failed_graph_fact_batches(self) -> int:
        return _sum_status(self.graph_fact_batches, "failed")

    @property
    def failed_surface_analysis_events(self) -> int:
        return _sum_status(self.surface_analysis_events, "failed")

    @property
    def dead_graph_fact_batches(self) -> int:
        return _sum_status(self.graph_fact_batches, "dead")

    @property
    def dead_surface_analysis_events(self) -> int:
        return _sum_status(self.surface_analysis_events, "dead")


class GraphProjectorStatusReader:
    """Read operational projection backlog without touching Neo4j.

    This is a visibility/readiness layer. It does not enqueue, apply, rebuild, or
    mutate projection rows. The report is intentionally based on durable
    PostgreSQL queues because NOTIFY and transient GDS graphs are not durable
    sources of truth.
    """

    def __init__(self, connection: StatusConnection) -> None:
        self._connection = connection

    def read(self, *, program_id: UUID | str | None = None) -> GraphProjectorStatusReport:
        return GraphProjectorStatusReport(
            projection_events=self._projection_event_counts(program_id=program_id),
            graph_fact_batches=self._graph_fact_batch_counts(program_id=program_id),
            surface_analysis_events=self._surface_analysis_event_counts(program_id=program_id),
            rebuild_sources=tuple(sorted(GRAPH_REBUILD_SOURCES)),
        )

    def _projection_event_counts(self, *, program_id: UUID | str | None) -> tuple[ProjectionEventStatusCount, ...]:
        rows = self._fetchall(
            """
SELECT source_type,
       event_type,
       status,
       count(*) AS count
FROM graph_projection_events
WHERE (%(program_id)s IS NULL OR program_id = %(program_id)s)
GROUP BY source_type, event_type, status
ORDER BY source_type ASC, event_type ASC, status ASC;
""".strip(),
            _program_filter_parameters(program_id),
        )
        return tuple(
            ProjectionEventStatusCount(
                source_type=str(row["source_type"]),
                event_type=str(row["event_type"]),
                status=str(row["status"]),
                count=int(row["count"]),
            )
            for row in rows
        )

    def _graph_fact_batch_counts(self, *, program_id: UUID | str | None) -> tuple[GraphFactBatchStatusCount, ...]:
        rows = self._fetchall(
            """
SELECT parser_version,
       status,
       count(*) AS count
FROM graph_fact_batches
WHERE (%(program_id)s IS NULL OR program_id = %(program_id)s)
GROUP BY parser_version, status
ORDER BY parser_version ASC, status ASC;
""".strip(),
            _program_filter_parameters(program_id),
        )
        return tuple(
            GraphFactBatchStatusCount(
                parser_version=str(row["parser_version"]),
                status=str(row["status"]),
                count=int(row["count"]),
            )
            for row in rows
        )

    def _surface_analysis_event_counts(self, *, program_id: UUID | str | None) -> tuple[SurfaceComponentAnalysisEventStatusCount, ...]:
        rows = self._fetchall(
            """
SELECT event_type,
       status,
       count(*) AS count
FROM surface_component_analysis_events
WHERE (%(program_id)s IS NULL OR program_id = %(program_id)s)
GROUP BY event_type, status
ORDER BY event_type ASC, status ASC;
""".strip(),
            _program_filter_parameters(program_id),
        )
        return tuple(
            SurfaceComponentAnalysisEventStatusCount(
                event_type=str(row["event_type"]),
                status=str(row["status"]),
                count=int(row["count"]),
            )
            for row in rows
        )

    def _fetchall(self, query: str, parameters: dict[str, object]) -> list[Mapping[str, Any]]:
        return _fetchall_rows(self._connection, query, parameters)


def _program_filter_parameters(program_id: UUID | str | None) -> dict[str, object]:
    return {"program_id": program_id}


def _sum_status(rows: tuple[ProjectionEventStatusCount, ...] | tuple[GraphFactBatchStatusCount, ...] | tuple[SurfaceComponentAnalysisEventStatusCount, ...], status: str) -> int:
    return sum(row.count for row in rows if row.status == status)
