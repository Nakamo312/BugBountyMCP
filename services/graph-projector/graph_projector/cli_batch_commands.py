from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .producers.action_outcomes import ActionOutcomeEnqueueLoopResult
from .producers.http_observations import HttpObservationEnqueueLoopResult
from .producers.javascript_references import JavaScriptReferenceEnqueueLoopResult
from .producers.raw_artifacts import RawArtifactEnqueueLoopResult
from .settings import GraphProjectorSettings
from .cli_services import (
    _build_action_outcome_enqueuer,
    _build_applicator,
    _build_graphfact_batch_notification_waiter,
    _build_http_observation_enqueuer,
    _build_javascript_reference_enqueuer,
    _build_projection_event_notification_waiter,
    _build_projection_event_worker,
    _build_raw_artifact_enqueuer,
    _build_rebuild_service,
)

_BuildEnqueuer = Callable[[GraphProjectorSettings], Any]


def apply_one(args) -> int:
    applicator = _build_applicator(GraphProjectorSettings.from_env())
    result = applicator.apply_one()
    print(f"graph-projector apply-one: status={result.status} batch_id={result.batch_id}")
    return 0 if result.status in {"applied", "empty"} else 1


def apply_loop(args) -> int:
    settings = GraphProjectorSettings.from_env()
    applicator = _build_applicator(settings)
    result = applicator.apply_loop(
        max_batches=args.max_batches,
        idle_exit_after=args.idle_exit_after,
        poll_seconds=settings.batch_poll_seconds if args.poll_seconds is None else args.poll_seconds,
        wait_for_notification=_build_graphfact_batch_notification_waiter(settings).wait,
    )
    print(
        "graph-projector apply-loop: "
        f"applied={result.applied} failed={result.failed} dead={result.dead} "
        f"empty={result.empty} iterations={result.iterations} last_status={result.last_status}"
    )
    return 0 if result.dead == 0 else 1


def _configured_value(settings: GraphProjectorSettings, attr_name: str, override):
    return getattr(settings, attr_name) if override is None else override


def _print_enqueue_result(label: str, result) -> None:
    print(
        f"graph-projector {label}: "
        f"scanned={result.scanned} enqueued={result.enqueued} skipped={result.skipped}"
    )


def _print_enqueue_loop_result(label: str, result) -> None:
    print(
        f"graph-projector {label}: "
        f"scanned={result.scanned} enqueued={result.enqueued} skipped={result.skipped} "
        f"empty={result.empty} iterations={result.iterations}"
    )


def _run_enqueue_once(
    args,
    *,
    label: str,
    build_enqueuer: _BuildEnqueuer,
    limit_setting: str,
) -> int:
    settings = GraphProjectorSettings.from_env()
    result = build_enqueuer(settings).enqueue_pending(
        limit=_configured_value(settings, limit_setting, args.limit),
        program_id=args.program_id,
    )
    _print_enqueue_result(label, result)
    return 0


def _run_enqueue_loop(
    args,
    *,
    label: str,
    build_enqueuer: _BuildEnqueuer,
    limit_setting: str,
    poll_setting: str,
    loop_result_type,
) -> int:
    settings = GraphProjectorSettings.from_env()
    result = loop_result_type.run(
        build_enqueuer(settings),
        limit=_configured_value(settings, limit_setting, args.limit),
        program_id=args.program_id,
        max_iterations=args.max_iterations,
        idle_exit_after=args.idle_exit_after,
        poll_seconds=_configured_value(settings, poll_setting, args.poll_seconds),
    )
    _print_enqueue_loop_result(label, result)
    return 0


def enqueue_raw_artifacts(args) -> int:
    return _run_enqueue_once(
        args,
        label="enqueue-raw-artifacts",
        build_enqueuer=_build_raw_artifact_enqueuer,
        limit_setting="raw_artifact_enqueue_limit",
    )


def enqueue_raw_artifacts_loop(args) -> int:
    return _run_enqueue_loop(
        args,
        label="enqueue-raw-artifacts-loop",
        build_enqueuer=_build_raw_artifact_enqueuer,
        limit_setting="raw_artifact_enqueue_limit",
        poll_setting="raw_artifact_enqueue_poll_seconds",
        loop_result_type=RawArtifactEnqueueLoopResult,
    )


def enqueue_http_observations(args) -> int:
    return _run_enqueue_once(
        args,
        label="enqueue-http-observations",
        build_enqueuer=_build_http_observation_enqueuer,
        limit_setting="http_observation_enqueue_limit",
    )


def enqueue_http_observations_loop(args) -> int:
    return _run_enqueue_loop(
        args,
        label="enqueue-http-observations-loop",
        build_enqueuer=_build_http_observation_enqueuer,
        limit_setting="http_observation_enqueue_limit",
        poll_setting="http_observation_enqueue_poll_seconds",
        loop_result_type=HttpObservationEnqueueLoopResult,
    )


def enqueue_javascript_references(args) -> int:
    return _run_enqueue_once(
        args,
        label="enqueue-javascript-references",
        build_enqueuer=_build_javascript_reference_enqueuer,
        limit_setting="javascript_reference_enqueue_limit",
    )


def enqueue_javascript_references_loop(args) -> int:
    return _run_enqueue_loop(
        args,
        label="enqueue-javascript-references-loop",
        build_enqueuer=_build_javascript_reference_enqueuer,
        limit_setting="javascript_reference_enqueue_limit",
        poll_setting="javascript_reference_enqueue_poll_seconds",
        loop_result_type=JavaScriptReferenceEnqueueLoopResult,
    )


def enqueue_action_outcomes(args) -> int:
    return _run_enqueue_once(
        args,
        label="enqueue-action-outcomes",
        build_enqueuer=_build_action_outcome_enqueuer,
        limit_setting="raw_artifact_enqueue_limit",
    )


def enqueue_action_outcomes_loop(args) -> int:
    return _run_enqueue_loop(
        args,
        label="enqueue-action-outcomes-loop",
        build_enqueuer=_build_action_outcome_enqueuer,
        limit_setting="raw_artifact_enqueue_limit",
        poll_setting="graph_projection_event_poll_seconds",
        loop_result_type=ActionOutcomeEnqueueLoopResult,
    )


def process_projection_events(args) -> int:
    settings = GraphProjectorSettings.from_env()
    worker = _build_projection_event_worker(settings)
    limit = settings.raw_artifact_enqueue_limit if args.limit is None else args.limit
    result = worker.process_once(limit=limit, program_id=args.program_id)
    print(
        "graph-projector process-projection-events: "
        f"scanned={result.scanned} enqueued={result.enqueued} skipped={result.skipped}"
    )
    return 0


def process_projection_events_loop(args) -> int:
    settings = GraphProjectorSettings.from_env()
    worker = _build_projection_event_worker(settings)
    limit = settings.raw_artifact_enqueue_limit if args.limit is None else args.limit
    poll_seconds = settings.graph_projection_event_poll_seconds if args.poll_seconds is None else args.poll_seconds

    if getattr(args, "bootstrap_rebuild", False):
        bootstrap_limit = (
            settings.bootstrap_rebuild_limit
            if getattr(args, "bootstrap_rebuild_limit", None) is None
            else args.bootstrap_rebuild_limit
        )
        bootstrap = _build_rebuild_service(settings).rebuild(
            limit=bootstrap_limit,
            program_id=args.program_id,
            reset_existing=False,
        )
        print(
            "graph-projector process-projection-events-loop bootstrap-rebuild: "
            f"raw_artifacts_scanned={bootstrap.raw_artifacts_scanned} "
            f"canonical_inventory_programs_scanned={bootstrap.canonical_inventory_programs_scanned} "
            f"http_observation_sources_scanned={bootstrap.http_observation_sources_scanned} "
            f"javascript_reference_sources_scanned={bootstrap.javascript_reference_sources_scanned} "
            f"action_outcomes_scanned={bootstrap.action_outcomes_scanned} "
            f"surface_snapshots_scanned={bootstrap.surface_snapshots_scanned} "
            f"enqueued={bootstrap.enqueued} skipped={bootstrap.skipped}"
        )

    result = worker.process_loop(
        limit=limit,
        program_id=args.program_id,
        max_iterations=args.max_iterations,
        idle_exit_after=args.idle_exit_after,
        poll_seconds=poll_seconds,
        wait_for_notification=_build_projection_event_notification_waiter(settings).wait,
    )
    print(
        "graph-projector process-projection-events-loop: "
        f"scanned={result.scanned} enqueued={result.enqueued} skipped={result.skipped} "
        f"empty={result.empty} iterations={result.iterations}"
    )
    return 0
