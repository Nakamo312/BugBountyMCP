"""Prometheus text metrics for durable pipeline orchestration state."""
from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import async_sessionmaker

from api.infrastructure.orchestration import pipeline_metrics_queries as queries
from api.infrastructure.orchestration.pipeline_metrics_rendering import (
    escape_label,
    format_sample,
    render_pipeline_metric_lines,
    unavailable_sample,
    worker_metric_lines,
)
from api.infrastructure.orchestration.pipeline_metrics_rows import collect_pipeline_metric_rows


class PipelineMetricsCollector:
    """Collect pipeline metrics from the durable `runs` table."""

    def __init__(
        self,
        session_factory: async_sessionmaker,
        *,
        worker_snapshots: Iterable[dict[str, Any]] | Callable[[], Iterable[dict[str, Any]]] | None = None,
        now: datetime | None = None,
        worker_heartbeat_ttl_seconds: int = 60,
    ):
        self.session_factory = session_factory
        self.worker_snapshots = worker_snapshots
        self.now = now
        self.worker_heartbeat_ttl_seconds = worker_heartbeat_ttl_seconds

    async def collect(self, *, program_id: UUID | None = None) -> str:
        rows = await collect_pipeline_metric_rows(self.session_factory, program_id=program_id)
        lines = render_pipeline_metric_lines(rows, worker_lines=self._worker_metric_lines())
        return "\n".join(lines) + "\n"

    def _worker_metric_lines(self) -> list[str]:
        return self.worker_metric_lines(
            self.worker_snapshots,
            now=self.now,
            worker_heartbeat_ttl_seconds=self.worker_heartbeat_ttl_seconds,
        )

    worker_metric_lines = staticmethod(worker_metric_lines)
    format_sample = staticmethod(format_sample)
    unavailable_sample = staticmethod(unavailable_sample)
    _escape_label = staticmethod(escape_label)
    _with_program_filter = staticmethod(queries.with_program_filter)

    _run_state_query = staticmethod(queries.run_state_query)
    _scheduled_queue_query = staticmethod(queries.scheduled_queue_query)
    _scheduled_state_query = staticmethod(queries.scheduled_state_query)
    _scheduled_state_oldest_age_query = staticmethod(queries.scheduled_state_oldest_age_query)
    _scheduled_work_dedup_query = staticmethod(queries.scheduled_work_dedup_query)
    _scheduled_leased_query = staticmethod(queries.scheduled_leased_query)
    _retry_due_query = staticmethod(queries.retry_due_query)
    _reconcile_query = staticmethod(queries.reconcile_query)
    _duration_query = staticmethod(queries.duration_query)
    _scheduled_oldest_age_query = staticmethod(queries.scheduled_oldest_age_query)
    _scheduled_leased_oldest_age_query = staticmethod(
        queries.scheduled_leased_oldest_age_query
    )
    _retry_due_oldest_age_query = staticmethod(queries.retry_due_oldest_age_query)
    _reconcile_oldest_age_query = staticmethod(queries.reconcile_oldest_age_query)
    _running_oldest_age_query = staticmethod(queries.running_oldest_age_query)
