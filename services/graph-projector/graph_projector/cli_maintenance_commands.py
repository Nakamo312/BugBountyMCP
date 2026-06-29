from __future__ import annotations

from .settings import GraphProjectorSettings
from .cli_services import (
    _build_rebuild_service,
    _build_retry_service,
)


def retry(args) -> int:
    settings = GraphProjectorSettings.from_env()
    service = _build_retry_service(settings)
    limit = settings.raw_artifact_enqueue_limit if args.limit is None else args.limit
    result = service.retry(
        queues=args.queues,
        statuses=args.statuses,
        limit=limit,
        program_id=args.program_id,
    )
    queue_label = ",".join(args.queues) if args.queues else "all"
    status_label = ",".join(args.statuses) if args.statuses else "failed,dead"
    print(
        "graph-projector retry: "
        f"queues={queue_label} statuses={status_label} "
        f"projection_events_reset={result.projection_events_reset} "
        f"graph_fact_batches_reset={result.graph_fact_batches_reset} "
        f"surface_analysis_events_reset={result.surface_analysis_events_reset} "
        f"total_reset={result.total_reset}"
    )
    return 0


def rebuild(args) -> int:
    settings = GraphProjectorSettings.from_env()
    service = _build_rebuild_service(settings)
    limit = settings.raw_artifact_enqueue_limit if args.limit is None else args.limit
    result = service.rebuild(limit=limit, program_id=args.program_id, sources=args.sources)
    source_label = ",".join(args.sources) if args.sources else "all"
    print(
        "graph-projector rebuild: "
        f"sources={source_label} "
        f"raw_artifacts_scanned={result.raw_artifacts_scanned} "
        f"canonical_inventory_programs_scanned={result.canonical_inventory_programs_scanned} "
        f"http_observation_sources_scanned={result.http_observation_sources_scanned} "
        f"javascript_reference_sources_scanned={result.javascript_reference_sources_scanned} "
        f"action_outcomes_scanned={result.action_outcomes_scanned} "
        f"surface_snapshots_scanned={result.surface_snapshots_scanned} "
        f"enqueued={result.enqueued} skipped={result.skipped}"
    )
    return 0
