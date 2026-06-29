"""Machine-readable readiness checks for search-indexer queues."""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from .status import SearchIndexerStatusReader


@dataclass(frozen=True)
class SearchIndexerHealthThresholds:
    max_pending_events: int = 0
    max_failed_events: int = 0
    max_dead_events: int = 0
    max_locked_events: int = 1000


@dataclass(frozen=True)
class SearchIndexerHealthCheck:
    ok: bool
    metrics: dict[str, int]
    violations: tuple[str, ...]
    thresholds: SearchIndexerHealthThresholds

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "metrics": self.metrics,
            "violations": list(self.violations),
            "thresholds": {
                "max_pending_events": self.thresholds.max_pending_events,
                "max_failed_events": self.thresholds.max_failed_events,
                "max_dead_events": self.thresholds.max_dead_events,
                "max_locked_events": self.thresholds.max_locked_events,
            },
        }


class SearchIndexerHealthChecker:
    def __init__(self, status_reader: SearchIndexerStatusReader) -> None:
        self._status_reader = status_reader

    def check(
        self,
        *,
        program_id: UUID | str | None = None,
        target: str | None = None,
        thresholds: SearchIndexerHealthThresholds | None = None,
    ) -> SearchIndexerHealthCheck:
        thresholds = thresholds or SearchIndexerHealthThresholds()
        report = self._status_reader.read(program_id=program_id, target=target)
        metrics = report.metrics()
        violations = _threshold_violations(metrics=metrics, thresholds=thresholds)
        return SearchIndexerHealthCheck(
            ok=not violations,
            metrics=metrics,
            violations=tuple(violations),
            thresholds=thresholds,
        )


def _threshold_violations(
    *,
    metrics: dict[str, int],
    thresholds: SearchIndexerHealthThresholds,
) -> list[str]:
    checks = [
        (
            "search_projection_events_pending",
            thresholds.max_pending_events,
            "search projection events pending backlog exceeds threshold",
        ),
        (
            "search_projection_events_failed",
            thresholds.max_failed_events,
            "search projection events failed backlog exceeds threshold",
        ),
        (
            "search_projection_events_dead",
            thresholds.max_dead_events,
            "search projection events dead backlog exceeds threshold",
        ),
        (
            "search_projection_events_locked",
            thresholds.max_locked_events,
            "search projection events locked backlog exceeds threshold",
        ),
    ]
    violations: list[str] = []
    for metric_name, threshold, message in checks:
        value = metrics[metric_name]
        if value > threshold:
            violations.append(f"{message}: {value} > {threshold}")
    return violations
