from __future__ import annotations

import sys

import pytest
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path("services/search-indexer").resolve()))

from search_indexer.diagnostics import SearchIndexerDiagnosticsReader  # noqa: E402
from search_indexer.health import SearchIndexerHealthChecker, SearchIndexerHealthThresholds  # noqa: E402
from search_indexer.reindex import build_parser  # noqa: E402
from search_indexer.retry import SearchIndexerRetryService  # noqa: E402
from search_indexer.status import SearchIndexerStatusReader  # noqa: E402


class QueueCursor:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query, parameters=None):
        self.calls.append((query, parameters or {}))

    def fetchall(self):
        return self.rows


class QueueConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def commit(self):
        return None

    def rollback(self):
        return None


class DiagnosticsCursor:
    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query, parameters=None):
        self.calls.append((query, parameters or {}))
        self.current_query = query

    def fetchall(self):
        if "GROUP BY target, source_type, status" in self.current_query:
            return [
                {"target": "surface-components", "source_type": "surface_component_analysis_run", "status": "failed", "count": 2},
                {"target": "surface-deltas", "source_type": "surface_snapshot", "status": "pending", "count": 1},
            ]
        if "FROM search_projection_events" in self.current_query and "WHERE status IN ('failed', 'dead')" in self.current_query:
            return [
                {
                    "id": "event-1",
                    "program_id": "program-1",
                    "target": "surface-components",
                    "source_type": "surface_component_analysis_run",
                    "source_id": "run-1",
                    "status": "failed",
                    "attempts": 3,
                    "last_error": "bulk failed",
                    "updated_at": "2026-06-27T00:00:00+00:00",
                }
            ]
        return []


class DiagnosticsConnection:
    def __init__(self):
        self.cursor_obj = DiagnosticsCursor()

    def cursor(self):
        return self.cursor_obj


def test_search_indexer_status_reader_reports_queue_counts() -> None:
    cursor = QueueCursor([
        {"target": "surface-components", "source_type": "surface_component_analysis_run", "status": "pending", "count": 3},
        {"target": "surface-deltas", "source_type": "surface_snapshot", "status": "failed", "count": 1},
    ])
    report = SearchIndexerStatusReader(QueueConnection(cursor)).read(program_id="00000000-0000-0000-0000-000000000001")

    assert report.pending_events == 3
    assert report.failed_events == 1
    assert "surface-components" in report.reindex_targets
    assert cursor.calls[0][1]["program_id"] == "00000000-0000-0000-0000-000000000001"


def test_search_indexer_health_checker_flags_failed_events() -> None:
    cursor = QueueCursor([
        {"target": "surface-components", "source_type": "surface_component_analysis_run", "status": "failed", "count": 2},
    ])
    check = SearchIndexerHealthChecker(SearchIndexerStatusReader(QueueConnection(cursor))).check(
        thresholds=SearchIndexerHealthThresholds(max_failed_events=0)
    )

    assert check.ok is False
    assert check.metrics["search_projection_events_failed"] == 2
    assert check.violations


def test_search_indexer_retry_resets_failed_dead_and_stale_locked_events() -> None:
    cursor = QueueCursor([{"id": "event-1"}, {"id": "event-2"}])
    result = SearchIndexerRetryService(QueueConnection(cursor)).retry(statuses=("failed", "dead"), limit=10, target="surface-components")

    assert result.total_reset == 2
    sql, params = cursor.calls[0]
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "status = 'pending'" in sql
    assert params["target"] == "surface-components"
    assert params["statuses"] == ["dead", "failed"]


def test_search_indexer_diagnostics_combines_health_and_samples() -> None:
    connection = DiagnosticsConnection()
    report = SearchIndexerDiagnosticsReader(connection).read(sample_limit=5)

    assert report.health.ok is False
    assert report.health.metrics["search_projection_events_failed"] == 2
    assert report.event_samples[0].id == "event-1"
    assert "python -m search_indexer retry" in report.suggested_commands()
    assert "python -m search_indexer process-events" in report.suggested_commands()


def test_search_indexer_cli_registers_status_retry_health_and_diagnostics() -> None:
    parser = build_parser()
    assert parser.parse_args(["status", "--json"]).command == "status"
    assert parser.parse_args(["retry", "--status", "failed", "--limit", "10"]).status == ["failed"]
    assert parser.parse_args(["health", "--max-pending-events", "3"]).max_pending_events == 3
    assert parser.parse_args(["diagnostics", "--sample-limit", "2", "--json"]).sample_limit == 2


def test_search_indexer_status_and_retry_reject_unknown_targets() -> None:
    cursor = QueueCursor([])
    with pytest.raises(ValueError, match="unsupported search-indexer target"):
        SearchIndexerStatusReader(QueueConnection(cursor)).read(target="missing-target")

    with pytest.raises(ValueError, match="unsupported search-indexer target"):
        SearchIndexerRetryService(QueueConnection(cursor)).retry(target="missing-target")
