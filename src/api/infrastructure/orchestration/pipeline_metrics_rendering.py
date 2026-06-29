"""Prometheus text rendering for durable pipeline metrics."""
from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from typing import Any

from api.infrastructure.orchestration.pipeline_metrics_rows import PipelineMetricRows


def render_pipeline_metric_lines(rows: PipelineMetricRows, *, worker_lines: list[str]) -> list[str]:
    lines = [
        "# HELP pipeline_metrics_available Whether durable pipeline metrics could be collected.",
        "# TYPE pipeline_metrics_available gauge",
        "pipeline_metrics_available 1",
        "# HELP pipeline_runs Durable pipeline runs grouped by node and state.",
        "# TYPE pipeline_runs gauge",
    ]
    for row in rows.run_rows:
        lines.append(
            format_sample(
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

    _append_scheduled_state_lines(lines, rows)
    _append_scheduled_work_dedup_lines(lines, rows)
    _append_queue_lines(lines, rows)
    _append_leased_lines(lines, rows)
    _append_retry_due_lines(lines, rows)
    _append_reconcile_lines(lines, rows)
    _append_duration_lines(lines, rows)
    _append_age_lines(lines, rows)
    lines.extend(worker_lines)
    return lines


def _append_scheduled_state_lines(lines: list[str], rows: PipelineMetricRows) -> None:
    lines.extend(
        [
            "# HELP pipeline_scheduled_state_runs Active scheduled runs grouped by node and state.",
            "# TYPE pipeline_scheduled_state_runs gauge",
        ]
    )
    for row in rows.scheduled_state_rows:
        lines.append(
            format_sample(
                "pipeline_scheduled_state_runs",
                {"node_id": row["node_id"] or "unknown", "status": row["status"]},
                row["count"],
            )
        )

    lines.extend(
        [
            "# HELP pipeline_scheduled_state_oldest_age_seconds Age of the oldest active scheduled run grouped by node and state.",
            "# TYPE pipeline_scheduled_state_oldest_age_seconds gauge",
        ]
    )
    for row in rows.scheduled_state_age_rows:
        lines.append(
            format_sample(
                "pipeline_scheduled_state_oldest_age_seconds",
                {"node_id": row["node_id"] or "unknown", "status": row["status"]},
                float(row["oldest_age_seconds"] or 0),
            )
        )
    if not rows.scheduled_state_age_rows:
        lines.append(format_sample("pipeline_scheduled_state_oldest_age_seconds", {}, 0))


def _append_scheduled_work_dedup_lines(lines: list[str], rows: PipelineMetricRows) -> None:
    lines.extend(
        [
            "# HELP pipeline_scheduled_work_dedup_total Duplicate scheduled work triggers coalesced into existing runs.",
            "# TYPE pipeline_scheduled_work_dedup_total counter",
        ]
    )
    for row in rows.dedup_rows:
        lines.append(
            format_sample(
                "pipeline_scheduled_work_dedup_total",
                {"node_id": row["node_id"] or "unknown"},
                int(row["count"] or 0),
            )
        )


def _append_queue_lines(lines: list[str], rows: PipelineMetricRows) -> None:
    lines.extend(
        [
            "# HELP pipeline_scheduled_queue_depth Queued scheduled node runs by node.",
            "# TYPE pipeline_scheduled_queue_depth gauge",
        ]
    )
    for row in rows.queue_rows:
        lines.append(
            format_sample(
                "pipeline_scheduled_queue_depth",
                {"node_id": row["node_id"] or "unknown"},
                row["count"],
            )
        )


def _append_leased_lines(lines: list[str], rows: PipelineMetricRows) -> None:
    lines.extend(
        [
            "# HELP pipeline_scheduled_leased_runs Leased scheduled node runs by node.",
            "# TYPE pipeline_scheduled_leased_runs gauge",
        ]
    )
    for row in rows.leased_rows:
        lines.append(
            format_sample(
                "pipeline_scheduled_leased_runs",
                {"node_id": row["node_id"] or "unknown"},
                row["count"],
            )
        )


def _append_retry_due_lines(lines: list[str], rows: PipelineMetricRows) -> None:
    lines.extend(
        [
            "# HELP pipeline_retry_due_runs Failed scheduled runs currently eligible for retry.",
            "# TYPE pipeline_retry_due_runs gauge",
        ]
    )
    for row in rows.retry_rows:
        lines.append(
            format_sample(
                "pipeline_retry_due_runs",
                {
                    "node_id": row["node_id"] or "unknown",
                    "retry_reason": row["retry_reason"] or "",
                },
                row["count"],
            )
        )


def _append_reconcile_lines(lines: list[str], rows: PipelineMetricRows) -> None:
    lines.extend(
        [
            "# HELP pipeline_reconcile_runs Runs requiring explicit reconcile.",
            "# TYPE pipeline_reconcile_runs gauge",
        ]
    )
    for row in rows.reconcile_rows:
        lines.append(
            format_sample(
                "pipeline_reconcile_runs",
                {
                    "node_id": row["node_id"] or "unknown",
                    "reconcile_reason": row["reconcile_reason"] or "",
                },
                row["count"],
            )
        )


def _append_duration_lines(lines: list[str], rows: PipelineMetricRows) -> None:
    lines.extend(
        [
            "# HELP pipeline_run_duration_seconds Completed run duration grouped by node and outcome.",
            "# TYPE pipeline_run_duration_seconds summary",
        ]
    )
    for row in rows.duration_rows:
        labels = {
            "node_id": row["node_id"] or "unknown",
            "terminal_outcome": row["terminal_outcome"] or "",
        }
        lines.append(format_sample("pipeline_run_duration_seconds_count", labels, row["count"]))
        lines.append(
            format_sample(
                "pipeline_run_duration_seconds_sum",
                labels,
                float(row["duration_seconds_sum"] or 0),
            )
        )


def _append_age_lines(lines: list[str], rows: PipelineMetricRows) -> None:
    _append_node_age_lines(
        lines,
        help_text="Age of the oldest queued scheduled node run.",
        metric_name="pipeline_scheduled_oldest_age_seconds",
        rows=rows.scheduled_age_rows,
    )
    _append_node_age_lines(
        lines,
        help_text="Age of the oldest leased scheduled node run.",
        metric_name="pipeline_scheduled_leased_oldest_age_seconds",
        rows=rows.leased_age_rows,
    )
    _append_reason_age_lines(
        lines,
        help_text="Age of the oldest retry-due scheduled run.",
        metric_name="pipeline_retry_due_oldest_age_seconds",
        reason_label="retry_reason",
        rows=rows.retry_age_rows,
    )
    _append_reason_age_lines(
        lines,
        help_text="Age of the oldest run requiring reconcile.",
        metric_name="pipeline_reconcile_oldest_age_seconds",
        reason_label="reconcile_reason",
        rows=rows.reconcile_age_rows,
    )
    lines.extend(
        [
            "# HELP pipeline_running_oldest_age_seconds Age of the oldest currently running durable run.",
            "# TYPE pipeline_running_oldest_age_seconds gauge",
        ]
    )
    for row in rows.running_age_rows:
        lines.append(
            format_sample(
                "pipeline_running_oldest_age_seconds",
                {"node_id": row["node_id"] or "unknown"},
                float(row["oldest_age_seconds"] or 0),
            )
        )


def _append_node_age_lines(
    lines: list[str],
    *,
    help_text: str,
    metric_name: str,
    rows: list[dict[str, Any]],
) -> None:
    lines.extend([f"# HELP {metric_name} {help_text}", f"# TYPE {metric_name} gauge"])
    for row in rows:
        lines.append(
            format_sample(
                metric_name,
                {"node_id": row["node_id"] or "unknown"},
                float(row["oldest_age_seconds"] or 0),
            )
        )
    if not rows:
        lines.append(format_sample(metric_name, {}, 0))


def _append_reason_age_lines(
    lines: list[str],
    *,
    help_text: str,
    metric_name: str,
    reason_label: str,
    rows: list[dict[str, Any]],
) -> None:
    lines.extend([f"# HELP {metric_name} {help_text}", f"# TYPE {metric_name} gauge"])
    for row in rows:
        lines.append(
            format_sample(
                metric_name,
                {
                    "node_id": row["node_id"] or "unknown",
                    reason_label: row[reason_label] or "",
                },
                float(row["oldest_age_seconds"] or 0),
            )
        )
    if not rows:
        lines.append(format_sample(metric_name, {}, 0))


def worker_metric_lines(
    worker_snapshots: Iterable[dict[str, Any]] | Callable[[], Iterable[dict[str, Any]]] | None,
    *,
    now: datetime | None = None,
    worker_heartbeat_ttl_seconds: int = 60,
) -> list[str]:
    snapshots_source = worker_snapshots
    if snapshots_source is None:
        return [
            "# HELP pipeline_worker_registry_available Whether the live worker registry is available to the metrics endpoint.",
            "# TYPE pipeline_worker_registry_available gauge",
            "pipeline_worker_registry_available 0",
            "# HELP pipeline_worker_registry_nodes Number of worker nodes in the live worker registry.",
            "# TYPE pipeline_worker_registry_nodes gauge",
            "pipeline_worker_registry_nodes 0",
        ]
    snapshots = snapshots_source() if callable(snapshots_source) else snapshots_source
    snapshots = list(snapshots)
    now_timestamp = (now or datetime.now(timezone.utc)).timestamp()
    lines = [
        "# HELP pipeline_worker_registry_available Whether the live worker registry is available to the metrics endpoint.",
        "# TYPE pipeline_worker_registry_available gauge",
        "pipeline_worker_registry_available 1",
        "# HELP pipeline_worker_registry_nodes Number of worker nodes in the live worker registry.",
        "# TYPE pipeline_worker_registry_nodes gauge",
        format_sample("pipeline_worker_registry_nodes", {}, len(snapshots)),
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
        up = (
            1
            if last_heartbeat and now_timestamp - last_heartbeat <= worker_heartbeat_ttl_seconds
            else 0
        )
        lines.append(
            format_sample(
                "pipeline_worker_configured",
                {"node_id": node_id},
                int(snapshot.get("configured", 1)),
            )
        )
        lines.append(
            format_sample(
                "pipeline_worker_capacity",
                {"node_id": node_id},
                int(snapshot.get("capacity", 0)),
            )
        )
        lines.append(
            format_sample(
                "pipeline_worker_busy",
                {"node_id": node_id},
                int(snapshot.get("busy", 0)),
            )
        )
        lines.append(
            format_sample(
                "pipeline_worker_last_heartbeat_timestamp_seconds",
                {"node_id": node_id},
                last_heartbeat,
            )
        )
        lines.append(format_sample("pipeline_worker_up", {"node_id": node_id}, up))
    return lines


def format_sample(name: str, labels: dict[str, Any], value: Any) -> str:
    label_text = ",".join(
        f'{key}="{escape_label(value)}"' for key, value in sorted(labels.items())
    )
    if label_text:
        return f"{name}{{{label_text}}} {value}"
    return f"{name} {value}"


def unavailable_sample() -> str:
    return (
        "# HELP pipeline_metrics_available Whether durable pipeline metrics could be collected.\n"
        "# TYPE pipeline_metrics_available gauge\n"
        "pipeline_metrics_available 0\n"
    )


def escape_label(value: Any) -> str:
    return str(value).replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
