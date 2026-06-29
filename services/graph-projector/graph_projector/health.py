from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from .status import GraphProjectorStatusReader


@dataclass(frozen=True)
class GraphProjectorHealthThresholds:
    max_pending_projection_events: int = 0
    max_pending_graph_fact_batches: int = 0
    max_failed_projection_events: int = 0
    max_failed_graph_fact_batches: int = 0
    max_dead_projection_events: int = 0
    max_dead_graph_fact_batches: int = 0
    max_pending_surface_analysis_events: int = 0
    max_failed_surface_analysis_events: int = 0
    max_dead_surface_analysis_events: int = 0

    def __post_init__(self) -> None:
        for field_name, value in self.__dict__.items():
            if int(value) < 0:
                raise ValueError(f"{field_name} must be non-negative")


@dataclass(frozen=True)
class GraphProjectorHealthCheck:
    ok: bool
    status: str
    reasons: tuple[str, ...]
    metrics: dict[str, int]
    thresholds: GraphProjectorHealthThresholds

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "reasons": list(self.reasons),
            "metrics": dict(self.metrics),
            "thresholds": {
                "max_pending_projection_events": self.thresholds.max_pending_projection_events,
                "max_pending_graph_fact_batches": self.thresholds.max_pending_graph_fact_batches,
                "max_failed_projection_events": self.thresholds.max_failed_projection_events,
                "max_failed_graph_fact_batches": self.thresholds.max_failed_graph_fact_batches,
                "max_dead_projection_events": self.thresholds.max_dead_projection_events,
                "max_dead_graph_fact_batches": self.thresholds.max_dead_graph_fact_batches,
                "max_pending_surface_analysis_events": self.thresholds.max_pending_surface_analysis_events,
                "max_failed_surface_analysis_events": self.thresholds.max_failed_surface_analysis_events,
                "max_dead_surface_analysis_events": self.thresholds.max_dead_surface_analysis_events,
            },
        }


class GraphProjectorHealthChecker:
    """Evaluate graph projector readiness from durable queue status.

    This is a gate/check layer. It does not retry, rebuild, apply, enqueue, or
    touch Neo4j. The check is intentionally computed from PostgreSQL durable
    queue state so CI/ops can fail fast when the projection pipeline falls
    behind or contains failed/dead rows.
    """

    def __init__(self, status_reader: GraphProjectorStatusReader) -> None:
        self._status_reader = status_reader

    def check(
        self,
        *,
        program_id: UUID | str | None = None,
        thresholds: GraphProjectorHealthThresholds | None = None,
    ) -> GraphProjectorHealthCheck:
        thresholds = thresholds or GraphProjectorHealthThresholds()
        report = self._status_reader.read(program_id=program_id)
        metrics = {
            "projection_events_pending": report.pending_projection_events,
            "projection_events_failed": report.failed_projection_events,
            "projection_events_dead": report.dead_projection_events,
            "graph_fact_batches_pending": report.pending_graph_fact_batches,
            "graph_fact_batches_failed": report.failed_graph_fact_batches,
            "graph_fact_batches_dead": report.dead_graph_fact_batches,
            "surface_analysis_events_pending": report.pending_surface_analysis_events,
            "surface_analysis_events_failed": report.failed_surface_analysis_events,
            "surface_analysis_events_dead": report.dead_surface_analysis_events,
        }
        reasons = tuple(_threshold_violations(metrics=metrics, thresholds=thresholds))
        return GraphProjectorHealthCheck(
            ok=not reasons,
            status="ok" if not reasons else "unhealthy",
            reasons=reasons,
            metrics=metrics,
            thresholds=thresholds,
        )


def _threshold_violations(
    *,
    metrics: dict[str, int],
    thresholds: GraphProjectorHealthThresholds,
) -> list[str]:
    checks = [
        (
            "projection_events_pending",
            thresholds.max_pending_projection_events,
            "projection events pending backlog exceeds threshold",
        ),
        (
            "graph_fact_batches_pending",
            thresholds.max_pending_graph_fact_batches,
            "graph fact batches pending backlog exceeds threshold",
        ),
        (
            "projection_events_failed",
            thresholds.max_failed_projection_events,
            "projection events failed backlog exceeds threshold",
        ),
        (
            "graph_fact_batches_failed",
            thresholds.max_failed_graph_fact_batches,
            "graph fact batches failed backlog exceeds threshold",
        ),
        (
            "projection_events_dead",
            thresholds.max_dead_projection_events,
            "projection events dead backlog exceeds threshold",
        ),
        (
            "graph_fact_batches_dead",
            thresholds.max_dead_graph_fact_batches,
            "graph fact batches dead backlog exceeds threshold",
        ),
        (
            "surface_analysis_events_pending",
            thresholds.max_pending_surface_analysis_events,
            "surface analysis events pending backlog exceeds threshold",
        ),
        (
            "surface_analysis_events_failed",
            thresholds.max_failed_surface_analysis_events,
            "surface analysis events failed backlog exceeds threshold",
        ),
        (
            "surface_analysis_events_dead",
            thresholds.max_dead_surface_analysis_events,
            "surface analysis events dead backlog exceeds threshold",
        ),
    ]
    violations: list[str] = []
    for metric_name, threshold, message in checks:
        value = metrics[metric_name]
        if value > threshold:
            violations.append(f"{message}: {value} > {threshold}")
    return violations
