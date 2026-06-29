"""Durable OpenSearch projection progress stored in PostgreSQL."""
from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

try:
    import psycopg2  # type: ignore
    from psycopg2.extras import RealDictCursor  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - optional until runtime DB operations
    class _MissingPsycopg2:
        def connect(self, _dsn: str):
            raise RuntimeError("psycopg2 is required for PostgreSQL projection state operations")

    psycopg2 = _MissingPsycopg2()  # type: ignore[assignment]
    RealDictCursor = object  # type: ignore[assignment]


def _connect(dsn: str):
    return psycopg2.connect(dsn)


@dataclass(frozen=True, slots=True)
class ProjectionRun:
    program_id: str
    projection_name: str
    source_watermark: str
    total_count: int


_INSERT_PROJECTION_WATERMARK_BOOTSTRAP = """
INSERT INTO projection_watermarks (
    id, program_id, projection_type, projection_name,
    source_watermark, lag_count, status
) VALUES (%s, %s, 'opensearch', %s, %s, %s, 'observed')
ON CONFLICT (program_id, projection_type, projection_name) DO NOTHING
""".strip()

_MARK_PROJECTION_WATERMARK_RUNNING = """
UPDATE projection_watermarks
SET status = 'running', last_error = NULL, updated_at = now()
WHERE program_id = %s
  AND projection_type = 'opensearch'
  AND projection_name = %s
RETURNING source_watermark
""".strip()

_MARK_PROJECTION_WATERMARK_LAGGING = """
UPDATE projection_watermarks
SET status = 'observed',
    lag_count = GREATEST(lag_count, %s),
    updated_at = now()
WHERE program_id = %s
  AND projection_type = 'opensearch'
  AND projection_name = %s
""".strip()

_MARK_PROJECTION_WATERMARK_READY = """
UPDATE projection_watermarks
SET status = 'ready',
    applied_watermark = source_watermark,
    lag_count = 0,
    applied_at = now(),
    updated_at = now(),
    last_error = NULL
WHERE program_id = %s
  AND projection_type = 'opensearch'
  AND projection_name = %s
  AND source_watermark = %s
""".strip()

_MARK_PROJECTION_WATERMARK_FAILED = """
UPDATE projection_watermarks
SET status = 'failed', last_error = %s, updated_at = now()
WHERE program_id = %s
  AND projection_type = 'opensearch'
  AND projection_name = %s
  AND source_watermark = %s
""".strip()


class ProjectionStateStore:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    def start(
        self,
        *,
        program_id: str,
        projection_name: str,
        total_count: int,
    ) -> ProjectionRun:
        if total_count < 0:
            raise ValueError("total_count must be non-negative")
        bootstrap_watermark = f"bootstrap:{total_count}"
        with _connect(self.dsn) as connection:
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    _INSERT_PROJECTION_WATERMARK_BOOTSTRAP,
                    (uuid4(), program_id, projection_name, bootstrap_watermark, total_count),
                )
                cursor.execute(
                    _MARK_PROJECTION_WATERMARK_RUNNING,
                    (program_id, projection_name),
                )
                row = cursor.fetchone()
        if row is None:
            raise RuntimeError("projection watermark disappeared while starting reindex")
        return ProjectionRun(
            program_id=program_id,
            projection_name=projection_name,
            source_watermark=str(row["source_watermark"]),
            total_count=total_count,
        )

    def complete(self, run: ProjectionRun, *, indexed_count: int) -> bool:
        if indexed_count < 0:
            raise ValueError("indexed_count must be non-negative")
        with _connect(self.dsn) as connection:
            with connection.cursor() as cursor:
                if indexed_count < run.total_count:
                    cursor.execute(
                        _MARK_PROJECTION_WATERMARK_LAGGING,
                        (run.total_count - indexed_count, run.program_id, run.projection_name),
                    )
                    return False
                cursor.execute(
                    _MARK_PROJECTION_WATERMARK_READY,
                    (run.program_id, run.projection_name, run.source_watermark),
                )
                return cursor.rowcount == 1

    def fail(self, run: ProjectionRun, *, error: str) -> None:
        with _connect(self.dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    _MARK_PROJECTION_WATERMARK_FAILED,
                    (_bounded_error(error), run.program_id, run.projection_name, run.source_watermark),
                )


def _bounded_error(error: str, *, limit: int = 4000) -> str:
    if limit <= 0:
        raise ValueError("limit must be positive")
    return error[:limit]
