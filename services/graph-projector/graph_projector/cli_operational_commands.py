from __future__ import annotations

import json

from .settings import GraphProjectorSettings
from .health import GraphProjectorHealthThresholds
from .cli_services import (
    _build_diagnostics_reader,
    _build_health_checker,
    _build_status_reader,
)


def check_config(args) -> int:
    settings = GraphProjectorSettings.from_env()
    print(
        "graph-projector config ok: "
        f"enabled={settings.neo4j_enabled} uri={settings.neo4j_uri} database={settings.neo4j_database}"
    )
    return 0


def status(args) -> int:
    settings = GraphProjectorSettings.from_env()
    report = _build_status_reader(settings).read(program_id=args.program_id)
    print(
        "graph-projector status: "
        f"projection_events_pending={report.pending_projection_events} "
        f"projection_events_failed={report.failed_projection_events} "
        f"projection_events_dead={report.dead_projection_events} "
        f"graph_fact_batches_pending={report.pending_graph_fact_batches} "
        f"graph_fact_batches_failed={report.failed_graph_fact_batches} "
        f"graph_fact_batches_dead={report.dead_graph_fact_batches} "
        f"surface_analysis_events_pending={report.pending_surface_analysis_events} "
        f"surface_analysis_events_failed={report.failed_surface_analysis_events} "
        f"surface_analysis_events_dead={report.dead_surface_analysis_events} "
        f"rebuild_sources={','.join(report.rebuild_sources)}"
    )
    for item in report.projection_events:
        print(
            "projection_event "
            f"source_type={item.source_type} event_type={item.event_type} "
            f"status={item.status} count={item.count}"
        )
    for item in report.graph_fact_batches:
        print(
            "graph_fact_batch "
            f"parser_version={item.parser_version} status={item.status} count={item.count}"
        )
    for item in report.surface_analysis_events:
        print(
            "surface_analysis_event "
            f"event_type={item.event_type} status={item.status} count={item.count}"
        )
    return 0


def diagnostics(args) -> int:
    settings = GraphProjectorSettings.from_env()
    thresholds = GraphProjectorHealthThresholds(
        max_pending_projection_events=args.max_pending_projection_events,
        max_pending_graph_fact_batches=args.max_pending_graph_fact_batches,
        max_failed_projection_events=args.max_failed_projection_events,
        max_failed_graph_fact_batches=args.max_failed_graph_fact_batches,
        max_dead_projection_events=args.max_dead_projection_events,
        max_dead_graph_fact_batches=args.max_dead_graph_fact_batches,
        max_pending_surface_analysis_events=args.max_pending_surface_analysis_events,
        max_failed_surface_analysis_events=args.max_failed_surface_analysis_events,
        max_dead_surface_analysis_events=args.max_dead_surface_analysis_events,
    )
    report = _build_diagnostics_reader(settings).read(
        program_id=args.program_id,
        thresholds=thresholds,
        sample_limit=args.sample_limit,
    )
    if args.json_output:
        print(json.dumps(report.to_dict(), sort_keys=True))
    else:
        health = report.health
        print(
            "graph-projector diagnostics: "
            f"status={health.status} "
            f"projection_events_pending={health.metrics['projection_events_pending']} "
            f"projection_events_failed={health.metrics['projection_events_failed']} "
            f"projection_events_dead={health.metrics['projection_events_dead']} "
            f"graph_fact_batches_pending={health.metrics['graph_fact_batches_pending']} "
            f"graph_fact_batches_failed={health.metrics['graph_fact_batches_failed']} "
            f"graph_fact_batches_dead={health.metrics['graph_fact_batches_dead']} "
            f"surface_analysis_events_pending={health.metrics['surface_analysis_events_pending']} "
            f"surface_analysis_events_failed={health.metrics['surface_analysis_events_failed']} "
            f"surface_analysis_events_dead={health.metrics['surface_analysis_events_dead']} "
            f"rebuild_sources={','.join(report.rebuild_sources)}"
        )
        for reason in health.reasons:
            print(f"diagnostic_health_violation {reason}")
        for command in report.suggested_commands():
            print(f"diagnostic_suggested_command {command}")
        for sample in report.projection_event_samples:
            print(
                "diagnostic_projection_event_sample "
                f"id={sample.id} source_type={sample.source_type} event_type={sample.event_type} "
                f"status={sample.status} attempts={sample.attempts} last_error={sample.last_error}"
            )
        for sample in report.graph_fact_batch_samples:
            print(
                "diagnostic_graph_fact_batch_sample "
                f"id={sample.id} parser_version={sample.parser_version} produced_by={sample.produced_by} "
                f"status={sample.status} attempts={sample.attempts} last_error={sample.last_error}"
            )
        for sample in report.surface_analysis_event_samples:
            print(
                "diagnostic_surface_analysis_event_sample "
                f"id={sample.id} snapshot_id={sample.snapshot_id} event_type={sample.event_type} "
                f"status={sample.status} attempts={sample.attempts} last_error={sample.last_error}"
            )
    return 0 if report.health.ok else 1


def health(args) -> int:
    settings = GraphProjectorSettings.from_env()
    thresholds = GraphProjectorHealthThresholds(
        max_pending_projection_events=args.max_pending_projection_events,
        max_pending_graph_fact_batches=args.max_pending_graph_fact_batches,
        max_failed_projection_events=args.max_failed_projection_events,
        max_failed_graph_fact_batches=args.max_failed_graph_fact_batches,
        max_dead_projection_events=args.max_dead_projection_events,
        max_dead_graph_fact_batches=args.max_dead_graph_fact_batches,
        max_pending_surface_analysis_events=args.max_pending_surface_analysis_events,
        max_failed_surface_analysis_events=args.max_failed_surface_analysis_events,
        max_dead_surface_analysis_events=args.max_dead_surface_analysis_events,
    )
    check = _build_health_checker(settings).check(program_id=args.program_id, thresholds=thresholds)
    if args.json_output:
        print(json.dumps(check.to_dict(), sort_keys=True))
    else:
        print(
            "graph-projector health: "
            f"status={check.status} "
            f"projection_events_pending={check.metrics['projection_events_pending']} "
            f"projection_events_failed={check.metrics['projection_events_failed']} "
            f"projection_events_dead={check.metrics['projection_events_dead']} "
            f"graph_fact_batches_pending={check.metrics['graph_fact_batches_pending']} "
            f"graph_fact_batches_failed={check.metrics['graph_fact_batches_failed']} "
            f"graph_fact_batches_dead={check.metrics['graph_fact_batches_dead']} "
            f"surface_analysis_events_pending={check.metrics['surface_analysis_events_pending']} "
            f"surface_analysis_events_failed={check.metrics['surface_analysis_events_failed']} "
            f"surface_analysis_events_dead={check.metrics['surface_analysis_events_dead']}"
        )
        for reason in check.reasons:
            print(f"health_violation {reason}")
    return 0 if check.ok else 1
