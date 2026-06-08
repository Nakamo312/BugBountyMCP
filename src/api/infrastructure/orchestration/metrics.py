"""Prometheus text metrics for durable pipeline orchestration state."""
from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from api.infrastructure.adapters.orm import runs


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
        async with self.session_factory() as session:
            run_rows = (
                await session.execute(self._run_state_query(program_id=program_id))
            ).mappings().all()
            queue_rows = (
                await session.execute(self._scheduled_queue_query(program_id=program_id))
            ).mappings().all()
            retry_rows = (
                await session.execute(self._retry_due_query(program_id=program_id))
            ).mappings().all()
            reconcile_rows = (
                await session.execute(self._reconcile_query(program_id=program_id))
            ).mappings().all()
            duration_rows = (
                await session.execute(self._duration_query(program_id=program_id))
            ).mappings().all()
            scheduled_age_rows = (
                await session.execute(self._scheduled_oldest_age_query(program_id=program_id))
            ).mappings().all()
            retry_age_rows = (
                await session.execute(self._retry_due_oldest_age_query(program_id=program_id))
            ).mappings().all()
            reconcile_age_rows = (
                await session.execute(self._reconcile_oldest_age_query(program_id=program_id))
            ).mappings().all()
            running_age_rows = (
                await session.execute(self._running_oldest_age_query(program_id=program_id))
            ).mappings().all()

        lines = [
            "# HELP pipeline_metrics_available Whether durable pipeline metrics could be collected.",
            "# TYPE pipeline_metrics_available gauge",
            "pipeline_metrics_available 1",
            "# HELP pipeline_runs Durable pipeline runs grouped by node and state.",
            "# TYPE pipeline_runs gauge",
        ]
        for row in run_rows:
            lines.append(
                self.format_sample(
                    "pipeline_runs",
                    {
                        "node_id": row["node_id"] or "unknown",
                        "status": row["status"],
                        "execution_mode": row["execution_mode"],
                        "terminal_outcome": row["terminal_outcome"] or "",
                        "needs_reconcile": str(bool(row["needs_reconcile"])).lower(),
                    },
                    row["count"],
                )
            )

        lines.extend(
            [
                "# HELP pipeline_scheduled_queue_depth Queued scheduled node runs by node.",
                "# TYPE pipeline_scheduled_queue_depth gauge",
            ]
        )
        for row in queue_rows:
            lines.append(
                self.format_sample(
                    "pipeline_scheduled_queue_depth",
                    {"node_id": row["node_id"] or "unknown"},
                    row["count"],
                )
            )

        lines.extend(
            [
                "# HELP pipeline_retry_due_runs Failed scheduled runs currently eligible for retry.",
                "# TYPE pipeline_retry_due_runs gauge",
            ]
        )
        for row in retry_rows:
            lines.append(
                self.format_sample(
                    "pipeline_retry_due_runs",
                    {
                        "node_id": row["node_id"] or "unknown",
                        "retry_reason": row["retry_reason"] or "",
                    },
                    row["count"],
                )
            )

        lines.extend(
            [
                "# HELP pipeline_reconcile_runs Runs requiring explicit reconcile.",
                "# TYPE pipeline_reconcile_runs gauge",
            ]
        )
        for row in reconcile_rows:
            lines.append(
                self.format_sample(
                    "pipeline_reconcile_runs",
                    {
                        "node_id": row["node_id"] or "unknown",
                        "reconcile_reason": row["reconcile_reason"] or "",
                    },
                    row["count"],
                )
            )

        lines.extend(
            [
                "# HELP pipeline_run_duration_seconds Completed run duration grouped by node and outcome.",
                "# TYPE pipeline_run_duration_seconds summary",
            ]
        )
        for row in duration_rows:
            labels = {
                "node_id": row["node_id"] or "unknown",
                "terminal_outcome": row["terminal_outcome"] or "",
            }
            lines.append(
                self.format_sample(
                    "pipeline_run_duration_seconds_count",
                    labels,
                    row["count"],
                )
            )
            lines.append(
                self.format_sample(
                    "pipeline_run_duration_seconds_sum",
                    labels,
                    float(row["duration_seconds_sum"] or 0),
                )
            )

        lines.extend(
            [
                "# HELP pipeline_scheduled_oldest_age_seconds Age of the oldest queued scheduled node run.",
                "# TYPE pipeline_scheduled_oldest_age_seconds gauge",
            ]
        )
        for row in scheduled_age_rows:
            lines.append(
                self.format_sample(
                    "pipeline_scheduled_oldest_age_seconds",
                    {"node_id": row["node_id"] or "unknown"},
                    float(row["oldest_age_seconds"] or 0),
                )
            )

        lines.extend(
            [
                "# HELP pipeline_retry_due_oldest_age_seconds Age of the oldest retry-due scheduled run.",
                "# TYPE pipeline_retry_due_oldest_age_seconds gauge",
            ]
        )
        for row in retry_age_rows:
            lines.append(
                self.format_sample(
                    "pipeline_retry_due_oldest_age_seconds",
                    {
                        "node_id": row["node_id"] or "unknown",
                        "retry_reason": row["retry_reason"] or "",
                    },
                    float(row["oldest_age_seconds"] or 0),
                )
            )

        lines.extend(
            [
                "# HELP pipeline_reconcile_oldest_age_seconds Age of the oldest run requiring reconcile.",
                "# TYPE pipeline_reconcile_oldest_age_seconds gauge",
            ]
        )
        for row in reconcile_age_rows:
            lines.append(
                self.format_sample(
                    "pipeline_reconcile_oldest_age_seconds",
                    {
                        "node_id": row["node_id"] or "unknown",
                        "reconcile_reason": row["reconcile_reason"] or "",
                    },
                    float(row["oldest_age_seconds"] or 0),
                )
            )

        lines.extend(
            [
                "# HELP pipeline_running_oldest_age_seconds Age of the oldest currently running durable run.",
                "# TYPE pipeline_running_oldest_age_seconds gauge",
            ]
        )
        for row in running_age_rows:
            lines.append(
                self.format_sample(
                    "pipeline_running_oldest_age_seconds",
                    {"node_id": row["node_id"] or "unknown"},
                    float(row["oldest_age_seconds"] or 0),
                )
            )

        lines.extend(self._worker_metric_lines())

        return "\n".join(lines) + "\n"

    def _worker_metric_lines(self) -> list[str]:
        snapshots_source = self.worker_snapshots
        if snapshots_source is None:
            return []
        snapshots = snapshots_source() if callable(snapshots_source) else snapshots_source
        now_timestamp = (self.now or datetime.now(timezone.utc)).timestamp()
        lines = [
            "# HELP pipeline_worker_configured Whether a worker node exists in the runtime registry.",
            "# TYPE pipeline_worker_configured gauge",
            "# HELP pipeline_worker_capacity Maximum concurrent runtime slots for a worker node.",
            "# TYPE pipeline_worker_capacity gauge",
            "# HELP pipeline_worker_busy Runtime slots currently busy for a worker node.",
            "# TYPE pipeline_worker_busy gauge",
            "# HELP pipeline_worker_last_heartbeat_timestamp_seconds Last worker heartbeat unix timestamp.",
            "# TYPE pipeline_worker_last_heartbeat_timestamp_seconds gauge",
            "# HELP pipeline_worker_up Whether the worker heartbeat is fresh.",
            "# TYPE pipeline_worker_up gauge",
        ]
        for snapshot in snapshots:
            node_id = snapshot.get("node_id") or "unknown"
            last_heartbeat = float(snapshot.get("last_heartbeat_timestamp_seconds") or 0)
            up = 1 if last_heartbeat and now_timestamp - last_heartbeat <= self.worker_heartbeat_ttl_seconds else 0
            lines.append(
                self.format_sample(
                    "pipeline_worker_configured",
                    {"node_id": node_id},
                    int(snapshot.get("configured", 1)),
                )
            )
            lines.append(
                self.format_sample(
                    "pipeline_worker_capacity",
                    {"node_id": node_id},
                    int(snapshot.get("capacity", 0)),
                )
            )
            lines.append(
                self.format_sample(
                    "pipeline_worker_busy",
                    {"node_id": node_id},
                    int(snapshot.get("busy", 0)),
                )
            )
            lines.append(
                self.format_sample(
                    "pipeline_worker_last_heartbeat_timestamp_seconds",
                    {"node_id": node_id},
                    last_heartbeat,
                )
            )
            lines.append(
                self.format_sample(
                    "pipeline_worker_up",
                    {"node_id": node_id},
                    up,
                )
            )
        return lines

    @staticmethod
    def format_sample(name: str, labels: dict[str, Any], value: Any) -> str:
        label_text = ",".join(
            f'{key}="{PipelineMetricsCollector._escape_label(value)}"'
            for key, value in sorted(labels.items())
        )
        if label_text:
            return f"{name}{{{label_text}}} {value}"
        return f"{name} {value}"

    @staticmethod
    def unavailable_sample() -> str:
        return (
            "# HELP pipeline_metrics_available Whether durable pipeline metrics could be collected.\n"
            "# TYPE pipeline_metrics_available gauge\n"
            "pipeline_metrics_available 0\n"
        )

    @staticmethod
    def _escape_label(value: Any) -> str:
        return (
            str(value)
            .replace("\\", "\\\\")
            .replace("\n", "\\n")
            .replace('"', '\\"')
        )

    @staticmethod
    def _with_program_filter(query, program_id: UUID | None):
        if program_id is None:
            return query
        return query.where(runs.c.program_id == program_id)

    @classmethod
    def _run_state_query(cls, *, program_id: UUID | None):
        query = (
            select(
                runs.c.node_id,
                runs.c.status,
                runs.c.execution_mode,
                runs.c.terminal_outcome,
                runs.c.needs_reconcile,
                func.count().label("count"),
            )
            .group_by(
                runs.c.node_id,
                runs.c.status,
                runs.c.execution_mode,
                runs.c.terminal_outcome,
                runs.c.needs_reconcile,
            )
            .order_by(runs.c.node_id, runs.c.status)
        )
        return cls._with_program_filter(query, program_id)

    @classmethod
    def _scheduled_queue_query(cls, *, program_id: UUID | None):
        query = (
            select(runs.c.node_id, func.count().label("count"))
            .where(
                runs.c.execution_mode == "scheduled",
                runs.c.status == "queued",
                runs.c.needs_reconcile.is_(False),
            )
            .group_by(runs.c.node_id)
            .order_by(runs.c.node_id)
        )
        return cls._with_program_filter(query, program_id)

    @classmethod
    def _retry_due_query(cls, *, program_id: UUID | None):
        now = datetime.now(timezone.utc)
        query = (
            select(
                runs.c.node_id,
                runs.c.retry_reason,
                func.count().label("count"),
            )
            .where(
                runs.c.execution_mode == "scheduled",
                runs.c.status == "failed",
                runs.c.retry_reason.is_not(None),
                runs.c.needs_reconcile.is_(False),
                or_(runs.c.next_retry_at.is_(None), runs.c.next_retry_at <= now),
            )
            .group_by(runs.c.node_id, runs.c.retry_reason)
            .order_by(runs.c.node_id, runs.c.retry_reason)
        )
        return cls._with_program_filter(query, program_id)

    @classmethod
    def _reconcile_query(cls, *, program_id: UUID | None):
        query = (
            select(
                runs.c.node_id,
                runs.c.reconcile_reason,
                func.count().label("count"),
            )
            .where(runs.c.needs_reconcile.is_(True))
            .group_by(runs.c.node_id, runs.c.reconcile_reason)
            .order_by(runs.c.node_id, runs.c.reconcile_reason)
        )
        return cls._with_program_filter(query, program_id)

    @classmethod
    def _duration_query(cls, *, program_id: UUID | None):
        duration_seconds = func.extract("epoch", runs.c.finished_at - runs.c.started_at)
        query = (
            select(
                runs.c.node_id,
                runs.c.terminal_outcome,
                func.count().label("count"),
                func.sum(duration_seconds).label("duration_seconds_sum"),
            )
            .where(
                runs.c.started_at.is_not(None),
                runs.c.finished_at.is_not(None),
            )
            .group_by(runs.c.node_id, runs.c.terminal_outcome)
            .order_by(runs.c.node_id, runs.c.terminal_outcome)
        )
        return cls._with_program_filter(query, program_id)

    @classmethod
    def _scheduled_oldest_age_query(cls, *, program_id: UUID | None):
        oldest_age = func.extract("epoch", func.now() - func.min(runs.c.created_at))
        query = (
            select(runs.c.node_id, oldest_age.label("oldest_age_seconds"))
            .where(
                runs.c.execution_mode == "scheduled",
                runs.c.status == "queued",
                runs.c.needs_reconcile.is_(False),
            )
            .group_by(runs.c.node_id)
            .order_by(runs.c.node_id)
        )
        return cls._with_program_filter(query, program_id)

    @classmethod
    def _retry_due_oldest_age_query(cls, *, program_id: UUID | None):
        now = datetime.now(timezone.utc)
        oldest_age = func.extract("epoch", func.now() - func.min(runs.c.next_retry_at))
        query = (
            select(
                runs.c.node_id,
                runs.c.retry_reason,
                oldest_age.label("oldest_age_seconds"),
            )
            .where(
                runs.c.execution_mode == "scheduled",
                runs.c.status == "failed",
                runs.c.retry_reason.is_not(None),
                runs.c.next_retry_at.is_not(None),
                runs.c.needs_reconcile.is_(False),
                runs.c.next_retry_at <= now,
            )
            .group_by(runs.c.node_id, runs.c.retry_reason)
            .order_by(runs.c.node_id, runs.c.retry_reason)
        )
        return cls._with_program_filter(query, program_id)

    @classmethod
    def _reconcile_oldest_age_query(cls, *, program_id: UUID | None):
        oldest_age = func.extract("epoch", func.now() - func.min(runs.c.updated_at))
        query = (
            select(
                runs.c.node_id,
                runs.c.reconcile_reason,
                oldest_age.label("oldest_age_seconds"),
            )
            .where(runs.c.needs_reconcile.is_(True))
            .group_by(runs.c.node_id, runs.c.reconcile_reason)
            .order_by(runs.c.node_id, runs.c.reconcile_reason)
        )
        return cls._with_program_filter(query, program_id)

    @classmethod
    def _running_oldest_age_query(cls, *, program_id: UUID | None):
        oldest_age = func.extract("epoch", func.now() - func.min(runs.c.started_at))
        query = (
            select(runs.c.node_id, oldest_age.label("oldest_age_seconds"))
            .where(
                runs.c.status == "running",
                runs.c.started_at.is_not(None),
            )
            .group_by(runs.c.node_id)
            .order_by(runs.c.node_id)
        )
        return cls._with_program_filter(query, program_id)
