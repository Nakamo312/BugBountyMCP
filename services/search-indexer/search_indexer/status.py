"""Read-only operational status for the OpenSearch projection event queue."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol
from uuid import UUID

from .target_contracts import SEARCH_INDEX_TARGETS, validate_optional_search_target


class StatusCursor(Protocol):
    def execute(self, query: str, parameters: dict[str, object] | None = None) -> object: ...
    def fetchall(self) -> list[Mapping[str, Any]]: ...


class StatusConnection(Protocol):
    def cursor(self) -> StatusCursor: ...


@dataclass(frozen=True)
class SearchProjectionEventStatusCount:
    target: str
    source_type: str
    status: str
    count: int


@dataclass(frozen=True)
class SearchIndexerStatusReport:
    projection_events: tuple[SearchProjectionEventStatusCount, ...]
    reindex_targets: tuple[str, ...]

    @property
    def pending_events(self) -> int:
        return _sum_status(self.projection_events, "pending")

    @property
    def locked_events(self) -> int:
        return _sum_status(self.projection_events, "locked")

    @property
    def failed_events(self) -> int:
        return _sum_status(self.projection_events, "failed")

    @property
    def dead_events(self) -> int:
        return _sum_status(self.projection_events, "dead")

    @property
    def processed_events(self) -> int:
        return _sum_status(self.projection_events, "processed")

    def metrics(self) -> dict[str, int]:
        return {
            "search_projection_events_pending": self.pending_events,
            "search_projection_events_locked": self.locked_events,
            "search_projection_events_failed": self.failed_events,
            "search_projection_events_dead": self.dead_events,
            "search_projection_events_processed": self.processed_events,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "metrics": self.metrics(),
            "reindex_targets": list(self.reindex_targets),
            "projection_events": [
                {
                    "target": row.target,
                    "source_type": row.source_type,
                    "status": row.status,
                    "count": row.count,
                }
                for row in self.projection_events
            ],
        }


class SearchIndexerStatusReader:
    """Read OpenSearch projection queue status without touching OpenSearch.

    This is a visibility layer around the durable PostgreSQL queue. It does not
    reindex, retry, enqueue, or mutate rows.
    """

    def __init__(self, connection: StatusConnection) -> None:
        self._connection = connection

    def read(
        self,
        *,
        program_id: UUID | str | None = None,
        target: str | None = None,
    ) -> SearchIndexerStatusReport:
        target = validate_optional_search_target(target)
        rows = self._fetchall(
            """
SELECT target,
       source_type,
       status,
       count(*) AS count
FROM search_projection_events
WHERE (%(program_id)s IS NULL OR program_id = %(program_id)s::uuid)
  AND (%(target)s IS NULL OR target = %(target)s)
GROUP BY target, source_type, status
ORDER BY target ASC, source_type ASC, status ASC;
""".strip(),
            {
                "program_id": None if program_id is None else str(program_id),
                "target": target,
            },
        )
        return SearchIndexerStatusReport(
            projection_events=tuple(
                SearchProjectionEventStatusCount(
                    target=str(row["target"]),
                    source_type=str(row["source_type"]),
                    status=str(row["status"]),
                    count=int(row["count"]),
                )
                for row in rows
            ),
            reindex_targets=tuple(SEARCH_INDEX_TARGETS),
        )

    def _fetchall(self, query: str, parameters: dict[str, object]) -> list[Mapping[str, Any]]:
        cursor = self._cursor()
        cursor.execute(query, parameters)
        return list(cursor.fetchall())

    def _cursor(self) -> StatusCursor:
        cursor = self._connection.cursor()
        if hasattr(cursor, "__enter__"):
            return cursor.__enter__()
        return cursor


def _sum_status(rows: tuple[SearchProjectionEventStatusCount, ...], status: str) -> int:
    return sum(row.count for row in rows if row.status == status)
