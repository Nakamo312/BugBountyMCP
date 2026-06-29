"""CLI parser and command handlers for search-indexer."""
from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from typing import Any

from search_indexer.reindex_ops import (
    connect_postgres,
    build_reindex_filters,
    run_cleanup,
    run_reindex,
)
from search_indexer.settings import load_settings
from search_indexer.target_contracts import SEARCH_INDEX_TARGETS

CommandHandler = Callable[[argparse.Namespace, argparse.ArgumentParser], int]


def _add_reindex_parser(subparsers: Any) -> None:
    reindex_parser = subparsers.add_parser("reindex")
    reindex_parser.add_argument("--target", choices=["all", *SEARCH_INDEX_TARGETS], default="all")
    reindex_parser.add_argument("--limit", type=int, default=1000)
    reindex_parser.add_argument("--batch-size", type=int, default=500)
    reindex_parser.add_argument("--program-id")
    reindex_parser.add_argument(
        "--analysis-run-id",
        help="Incremental surface-components filter for one materialized analysis run.",
    )
    reindex_parser.add_argument(
        "--snapshot-id",
        help="Incremental surface filter: component snapshot_id or delta to_snapshot_id.",
    )


def _add_projection_event_parsers(
    subparsers: Any,
) -> None:
    process_events = subparsers.add_parser(
        "process-events",
        help="Process pending OpenSearch projection events.",
    )
    process_events.add_argument("--program-id")
    process_events.add_argument("--target", choices=["surface-components", "surface-deltas"], default=None)
    process_events.add_argument("--limit", type=int, default=100)
    process_events.add_argument("--batch-size", type=int, default=500)
    process_events.add_argument("--worker-id", default="search-indexer-cli")
    process_events.add_argument("--lock-seconds", type=int, default=300)
    process_events.add_argument("--max-attempts", type=int, default=5)

    process_events_loop = subparsers.add_parser(
        "process-events-loop",
        help="Continuously process OpenSearch projection events.",
    )
    process_events_loop.add_argument("--program-id")
    process_events_loop.add_argument("--target", choices=["surface-components", "surface-deltas"], default=None)
    process_events_loop.add_argument("--max-events", type=int, default=None)
    process_events_loop.add_argument("--batch-size", type=int, default=500)
    process_events_loop.add_argument("--worker-id", default="search-indexer-cli")
    process_events_loop.add_argument("--lock-seconds", type=int, default=300)
    process_events_loop.add_argument("--max-attempts", type=int, default=5)
    process_events_loop.add_argument("--idle-exit-after", type=int, default=None)
    process_events_loop.add_argument("--poll-seconds", type=float, default=1.0)


def _add_status_parser(subparsers: Any) -> None:
    status_parser = subparsers.add_parser("status", help="Show OpenSearch projection event queue status.")
    status_parser.add_argument("--program-id")
    status_parser.add_argument("--target", choices=list(SEARCH_INDEX_TARGETS), default=None)
    status_parser.add_argument("--json", action="store_true")


def _add_retry_parser(subparsers: Any) -> None:
    retry_parser = subparsers.add_parser(
        "retry",
        help="Reset failed/dead/stale locked search projection events to pending.",
    )
    retry_parser.add_argument("--program-id")
    retry_parser.add_argument("--target", choices=list(SEARCH_INDEX_TARGETS), default=None)
    retry_parser.add_argument("--status", action="append", choices=["failed", "dead", "locked"], default=None)
    retry_parser.add_argument("--limit", type=int, default=1000)


def _add_health_parser(subparsers: Any) -> None:
    health_parser = subparsers.add_parser("health", help="Check OpenSearch projection queue health.")
    health_parser.add_argument("--program-id")
    health_parser.add_argument("--target", choices=list(SEARCH_INDEX_TARGETS), default=None)
    health_parser.add_argument("--max-pending-events", type=int, default=0)
    health_parser.add_argument("--max-failed-events", type=int, default=0)
    health_parser.add_argument("--max-dead-events", type=int, default=0)
    health_parser.add_argument("--max-locked-events", type=int, default=1000)
    health_parser.add_argument("--json", action="store_true")


def _add_diagnostics_parser(subparsers: Any) -> None:
    diagnostics_parser = subparsers.add_parser(
        "diagnostics",
        help="Show read-only OpenSearch projection diagnostics.",
    )
    diagnostics_parser.add_argument("--program-id")
    diagnostics_parser.add_argument("--target", choices=list(SEARCH_INDEX_TARGETS), default=None)
    diagnostics_parser.add_argument("--sample-limit", type=int, default=5)
    diagnostics_parser.add_argument("--max-pending-events", type=int, default=0)
    diagnostics_parser.add_argument("--max-failed-events", type=int, default=0)
    diagnostics_parser.add_argument("--max-dead-events", type=int, default=0)
    diagnostics_parser.add_argument("--max-locked-events", type=int, default=1000)
    diagnostics_parser.add_argument("--json", action="store_true")


def _add_cleanup_parser(subparsers: Any) -> None:
    cleanup_parser = subparsers.add_parser("cleanup-indexes")
    cleanup_parser.add_argument("--target", choices=["all", *SEARCH_INDEX_TARGETS], default="all")
    cleanup_parser.add_argument(
        "--yes",
        action="store_true",
        help="Required confirmation for deleting rebuildable OpenSearch indexes.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="search_indexer")
    subparsers = parser.add_subparsers(dest="command", required=True)
    _add_reindex_parser(subparsers)
    _add_projection_event_parsers(subparsers)
    _add_status_parser(subparsers)
    _add_retry_parser(subparsers)
    _add_health_parser(subparsers)
    _add_diagnostics_parser(subparsers)
    _add_cleanup_parser(subparsers)
    return parser


def handle_reindex(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    try:
        filters = build_reindex_filters(
            target=args.target,
            analysis_run_id=args.analysis_run_id,
            snapshot_id=args.snapshot_id,
        )
    except ValueError as exc:
        parser.error(str(exc))
    results = run_reindex(
        settings=load_settings(),
        target=args.target,
        limit=args.limit,
        batch_size=args.batch_size,
        program_id=args.program_id,
        filters=filters,
    )
    for name, count in results.items():
        print(f"{name}: indexed {count}")
    return 0


def _projection_worker(args: argparse.Namespace, *, limit: int):
    from search_indexer.events import SearchProjectionEventStore, SearchProjectionEventWorker

    settings = load_settings()
    return SearchProjectionEventWorker(
        settings=settings,
        event_store=SearchProjectionEventStore(settings.postgres_dsn),
        worker_id=args.worker_id,
        lock_seconds=args.lock_seconds,
        max_attempts=args.max_attempts,
        limit=limit,
        batch_size=args.batch_size,
    )


def handle_process_events(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    worker = _projection_worker(args, limit=args.limit)
    processed = failed = dead = empty = 0
    last_status = None
    for _ in range(args.limit):
        result = worker.process_one(program_id=args.program_id, target=args.target)
        last_status = result.status
        if result.status == "processed":
            processed += 1
        elif result.status == "failed":
            failed += 1
        elif result.status == "dead":
            dead += 1
        elif result.status == "empty":
            empty += 1
            break
    print(
        "search-indexer process-events: "
        f"processed={processed} failed={failed} dead={dead} empty={empty} last_status={last_status}"
    )
    return 0 if dead == 0 else 1


def handle_process_events_loop(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    worker = _projection_worker(args, limit=1000)
    result = worker.process_loop(
        program_id=args.program_id,
        target=args.target,
        max_events=args.max_events,
        idle_exit_after=args.idle_exit_after,
        poll_seconds=args.poll_seconds,
    )
    print(
        "search-indexer process-events-loop: "
        f"processed={result.processed} failed={result.failed} dead={result.dead} "
        f"empty={result.empty} iterations={result.iterations} last_status={result.last_status}"
    )
    return 0 if result.dead == 0 else 1


def handle_status(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from search_indexer.status import SearchIndexerStatusReader

    settings = load_settings()
    with connect_postgres(settings.postgres_dsn) as connection:
        report = SearchIndexerStatusReader(connection).read(program_id=args.program_id, target=args.target)
    if args.json:
        print(json.dumps(report.to_dict(), sort_keys=True))
        return 0
    metrics = report.metrics()
    print(
        "search-indexer status: "
        f"pending={metrics['search_projection_events_pending']} "
        f"locked={metrics['search_projection_events_locked']} "
        f"failed={metrics['search_projection_events_failed']} "
        f"dead={metrics['search_projection_events_dead']} "
        f"processed={metrics['search_projection_events_processed']}"
    )
    print("reindex_targets=" + ",".join(report.reindex_targets))
    for row in report.projection_events:
        print(
            "search_projection_event "
            f"target={row.target} source_type={row.source_type} status={row.status} count={row.count}"
        )
    return 0


def handle_retry(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from search_indexer.retry import SearchIndexerRetryService

    settings = load_settings()
    with connect_postgres(settings.postgres_dsn) as connection:
        result = SearchIndexerRetryService(connection).retry(
            statuses=args.status,
            limit=args.limit,
            program_id=args.program_id,
            target=args.target,
        )
    print(f"search-indexer retry: events_reset={result.events_reset} total_reset={result.total_reset}")
    return 0


def _health_thresholds(args: argparse.Namespace):
    from search_indexer.health import SearchIndexerHealthThresholds

    return SearchIndexerHealthThresholds(
        max_pending_events=args.max_pending_events,
        max_failed_events=args.max_failed_events,
        max_dead_events=args.max_dead_events,
        max_locked_events=args.max_locked_events,
    )


def handle_health(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from search_indexer.health import SearchIndexerHealthChecker
    from search_indexer.status import SearchIndexerStatusReader

    settings = load_settings()
    with connect_postgres(settings.postgres_dsn) as connection:
        check = SearchIndexerHealthChecker(SearchIndexerStatusReader(connection)).check(
            program_id=args.program_id,
            target=args.target,
            thresholds=_health_thresholds(args),
        )
    if args.json:
        print(json.dumps(check.to_dict(), sort_keys=True))
    else:
        print("search-indexer health: " + ("ok" if check.ok else "unhealthy"))
        for name, value in sorted(check.metrics.items()):
            print(f"{name}={value}")
        for violation in check.violations:
            print(f"violation: {violation}")
    return 0 if check.ok else 1


def handle_diagnostics(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from search_indexer.diagnostics import SearchIndexerDiagnosticsReader

    settings = load_settings()
    with connect_postgres(settings.postgres_dsn) as connection:
        report = SearchIndexerDiagnosticsReader(connection).read(
            program_id=args.program_id,
            target=args.target,
            thresholds=_health_thresholds(args),
            sample_limit=args.sample_limit,
        )
    if args.json:
        print(json.dumps(report.to_dict(), sort_keys=True))
    else:
        print("search-indexer diagnostics: " + ("ok" if report.health.ok else "unhealthy"))
        for name, value in sorted(report.health.metrics.items()):
            print(f"{name}={value}")
        for violation in report.health.violations:
            print(f"violation: {violation}")
        for sample in report.event_samples:
            print(
                "search_projection_event_sample "
                f"id={sample.id} target={sample.target} status={sample.status} attempts={sample.attempts}"
            )
        if report.suggested_commands():
            print("suggested_commands=" + ";".join(report.suggested_commands()))
    return 0 if report.health.ok else 1


def handle_cleanup_indexes(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if not args.yes:
        parser.error("cleanup-indexes requires --yes")
    deleted = run_cleanup(settings=load_settings(), target=args.target)
    for index_name in deleted:
        print(f"deleted index: {index_name}")
    return 0


COMMAND_HANDLERS: dict[str, CommandHandler] = {
    "reindex": handle_reindex,
    "process-events": handle_process_events,
    "process-events-loop": handle_process_events_loop,
    "status": handle_status,
    "retry": handle_retry,
    "health": handle_health,
    "diagnostics": handle_diagnostics,
    "cleanup-indexes": handle_cleanup_indexes,
}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = COMMAND_HANDLERS.get(args.command)
    if handler is None:
        parser.error(f"Unsupported command: {args.command}")
        return 2
    return handler(args, parser)
