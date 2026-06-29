from __future__ import annotations

import json

from .action_experience_proposals import ActionExperienceProposalLoopResult
from .settings import GraphProjectorSettings
from .cli_output import _print_surface_component_report
from .cli_services import (
    _build_action_experience_proposal_worker,
    _build_surface_component_analysis_event_worker,
    _build_surface_component_analysis_store,
    _build_surface_component_report_reader,
)


def propose_action_experience(args) -> int:
    settings = GraphProjectorSettings.from_env()
    worker = _build_action_experience_proposal_worker(
        settings,
        candidate_limit=args.candidate_limit,
        similarity_cutoff=args.similarity_cutoff,
    )
    limit = settings.action_experience_proposal_limit if args.limit is None else args.limit
    result = worker.propose_once(limit=limit, program_id=args.program_id)
    print(
        "graph-projector propose-action-experience: "
        f"scanned={result.scanned} proposal_runs={result.proposal_runs} "
        f"proposals={result.proposals} no_candidates={result.no_candidates} failed={result.failed}"
    )
    return 0 if result.failed == 0 else 1


def propose_action_experience_loop(args) -> int:
    settings = GraphProjectorSettings.from_env()
    worker = _build_action_experience_proposal_worker(
        settings,
        candidate_limit=args.candidate_limit,
        similarity_cutoff=args.similarity_cutoff,
    )
    limit = settings.action_experience_proposal_limit if args.limit is None else args.limit
    poll_seconds = (
        settings.action_experience_proposal_poll_seconds
        if args.poll_seconds is None
        else args.poll_seconds
    )
    result = ActionExperienceProposalLoopResult.run(
        worker,
        limit=limit,
        program_id=args.program_id,
        max_iterations=args.max_iterations,
        idle_exit_after=args.idle_exit_after,
        poll_seconds=poll_seconds,
    )
    print(
        "graph-projector propose-action-experience-loop: "
        f"scanned={result.scanned} proposal_runs={result.proposal_runs} "
        f"proposals={result.proposals} no_candidates={result.no_candidates} "
        f"failed={result.failed} empty={result.empty} iterations={result.iterations}"
    )
    return 0 if result.failed == 0 else 1


def surface_components(args) -> int:
    settings = GraphProjectorSettings.from_env()
    reader = _build_surface_component_report_reader(settings)
    report = reader.read(
        program_id=args.program_id,
        snapshot_id=args.snapshot_id,
        previous_snapshot_id=args.previous_snapshot_id,
        limit=args.limit,
        include_action_candidates=not args.no_action_candidates,
        candidate_limit=args.candidate_limit,
        component_limit=args.component_limit,
        similarity_cutoff=args.similarity_cutoff,
    )
    if args.json_output:
        print(json.dumps(report.to_dict(), sort_keys=True))
    else:
        _print_surface_component_report(report)
    return 0


def surface_components_materialize(args) -> int:
    settings = GraphProjectorSettings.from_env()
    reader = _build_surface_component_report_reader(settings)
    report = reader.read(
        program_id=args.program_id,
        snapshot_id=args.snapshot_id,
        previous_snapshot_id=args.previous_snapshot_id,
        limit=args.limit,
        include_action_candidates=not args.no_action_candidates,
        candidate_limit=args.candidate_limit,
        component_limit=args.component_limit,
        similarity_cutoff=args.similarity_cutoff,
    )
    result = _build_surface_component_analysis_store(settings).materialize(
        report,
        settings_json={
            "limit": args.limit,
            "candidate_limit": args.candidate_limit,
            "component_limit": args.component_limit,
            "similarity_cutoff": args.similarity_cutoff,
            "include_action_candidates": not args.no_action_candidates,
        },
    )
    if args.json_output:
        print(json.dumps(result.to_dict(), sort_keys=True))
    else:
        print(
            "graph-projector surface-components-materialize: "
            f"analysis_run_id={result.analysis_run_id} program_id={result.program_id} "
            f"snapshot_id={result.snapshot_id} previous_snapshot_id={result.previous_snapshot_id or '-'} "
            f"items={result.item_count} action_candidates={result.action_candidate_count} "
            f"report_fingerprint={result.report_fingerprint}"
        )
    return 0


def surface_components_materialized(args) -> int:
    settings = GraphProjectorSettings.from_env()
    report = _build_surface_component_analysis_store(settings).latest(
        program_id=args.program_id,
        snapshot_id=args.snapshot_id,
        previous_snapshot_id=args.previous_snapshot_id,
    )
    if report is None:
        print(
            "graph-projector surface-components-materialized: "
            f"program_id={args.program_id} snapshot_id={args.snapshot_id} previous_snapshot_id={args.previous_snapshot_id or '-'} found=false"
        )
        return 1
    if args.json_output:
        print(json.dumps(report.to_dict(), sort_keys=True))
    else:
        print(
            "graph-projector surface-components-materialized: "
            f"analysis_run_id={report.analysis_run_id} program_id={report.program_id} "
            f"snapshot_id={report.snapshot_id} previous_snapshot_id={report.previous_snapshot_id or '-'} "
            f"items={report.item_count} report_fingerprint={report.report_fingerprint}"
        )
        for item in report.items:
            print(
                "surface_component_materialized_item "
                f"component_id={item.component_id} node_count={item.node_count} "
                f"changed_node_count={item.changed_node_count} "
                f"structural_pressure_score={item.structural_pressure_score} "
                f"drift_score={item.drift_score} bridge_pressure_score={item.bridge_pressure_score} "
                f"outlier_score={item.outlier_score} exploration_priority_score={item.exploration_priority_score} "
                f"action_candidate_count={item.action_candidate_count}"
            )
    return 0


def process_surface_analysis_events(args) -> int:
    settings = GraphProjectorSettings.from_env()
    worker = _build_surface_component_analysis_event_worker(settings)
    limit = settings.raw_artifact_enqueue_limit if args.limit is None else args.limit
    processed = failed = dead = empty = 0
    last_status = None
    for _ in range(limit):
        result = worker.process_one(program_id=args.program_id)
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
        "graph-projector process-surface-analysis-events: "
        f"processed={processed} failed={failed} dead={dead} empty={empty} last_status={last_status}"
    )
    return 0 if dead == 0 else 1


def process_surface_analysis_events_loop(args) -> int:
    settings = GraphProjectorSettings.from_env()
    worker = _build_surface_component_analysis_event_worker(settings)
    result = worker.process_loop(
        program_id=args.program_id,
        max_events=args.max_events,
        idle_exit_after=args.idle_exit_after,
        poll_seconds=settings.batch_poll_seconds if args.poll_seconds is None else args.poll_seconds,
    )
    print(
        "graph-projector process-surface-analysis-events-loop: "
        f"processed={result.processed} failed={result.failed} dead={result.dead} "
        f"empty={result.empty} iterations={result.iterations} last_status={result.last_status}"
    )
    return 0 if result.dead == 0 else 1
