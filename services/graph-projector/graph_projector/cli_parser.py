from __future__ import annotations

import argparse

from .rebuild import GRAPH_REBUILD_SOURCES
from .retry import GRAPH_PROJECTOR_RETRY_QUEUES, GRAPH_PROJECTOR_RETRY_STATUSES


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="graph-projector")
    subparsers = parser.add_subparsers(dest="command", required=True)
    _add_operational_commands(subparsers)
    _add_batch_commands(subparsers)
    _add_experience_commands(subparsers)
    _add_surface_commands(subparsers)
    _add_maintenance_commands(subparsers)
    return parser


def _add_operational_commands(subparsers) -> None:
    subparsers.add_parser("check-config", help="Validate graph projector settings without projecting data.")
    status = subparsers.add_parser("status", help="Show durable projection backlog and rebuild source visibility.")
    status.add_argument("--program-id", default=None)

    diagnostics = subparsers.add_parser("diagnostics", help="Emit a read-only graph projector diagnostics snapshot for CI/ops debugging.")
    diagnostics.add_argument("--program-id", default=None)
    diagnostics.add_argument("--sample-limit", type=int, default=5)
    _add_queue_threshold_arguments(diagnostics)
    diagnostics.add_argument("--json", action="store_true", dest="json_output")

    health = subparsers.add_parser("health", help="Check graph projector durable queue readiness for CI/ops gates.")
    health.add_argument("--program-id", default=None)
    _add_queue_threshold_arguments(health)
    health.add_argument("--json", action="store_true", dest="json_output")


def _add_batch_commands(subparsers) -> None:
    subparsers.add_parser("apply-one", help="Claim and apply one pending GraphFactBatch to Neo4j.")
    apply_loop = subparsers.add_parser("apply-loop", help="Continuously claim and apply pending GraphFactBatch rows.")
    apply_loop.add_argument("--max-batches", type=int, default=None)
    apply_loop.add_argument("--idle-exit-after", type=int, default=None)
    apply_loop.add_argument("--poll-seconds", type=float, default=None)

    enqueue_raw_artifacts = subparsers.add_parser("enqueue-raw-artifacts", help="Enqueue GraphFactBatch rows from raw_artifacts metadata.")
    _add_limit_program_arguments(enqueue_raw_artifacts)
    enqueue_raw_artifacts_loop = subparsers.add_parser("enqueue-raw-artifacts-loop", help="Continuously enqueue GraphFactBatch rows from raw_artifacts metadata.")
    _add_enqueue_loop_arguments(enqueue_raw_artifacts_loop)

    enqueue_http_observations = subparsers.add_parser("enqueue-http-observations", help="Enqueue GraphFactBatch rows from canonical HTTP observations.")
    _add_limit_program_arguments(enqueue_http_observations)
    enqueue_http_observations_loop = subparsers.add_parser("enqueue-http-observations-loop", help="Continuously enqueue GraphFactBatch rows from canonical HTTP observations.")
    _add_enqueue_loop_arguments(enqueue_http_observations_loop)

    enqueue_javascript_references = subparsers.add_parser("enqueue-javascript-references", help="Enqueue GraphFactBatch rows from canonical JavaScript references.")
    _add_limit_program_arguments(enqueue_javascript_references)
    enqueue_javascript_references_loop = subparsers.add_parser("enqueue-javascript-references-loop", help="Continuously enqueue GraphFactBatch rows from canonical JavaScript references.")
    _add_enqueue_loop_arguments(enqueue_javascript_references_loop)

    enqueue_action_outcomes = subparsers.add_parser("enqueue-action-outcomes", help="Enqueue GraphFactBatch rows from action outcome memory.")
    _add_limit_program_arguments(enqueue_action_outcomes)
    enqueue_action_outcomes_loop = subparsers.add_parser("enqueue-action-outcomes-loop", help="Continuously enqueue GraphFactBatch rows from action outcome memory.")
    _add_enqueue_loop_arguments(enqueue_action_outcomes_loop)

    process_projection_events = subparsers.add_parser("process-projection-events", help="Process pending graph_projection_events through the registered GraphFact producers.")
    _add_limit_program_arguments(process_projection_events)
    process_projection_events_loop = subparsers.add_parser("process-projection-events-loop", help="Continuously process pending graph_projection_events through the registered GraphFact producers.")
    _add_enqueue_loop_arguments(process_projection_events_loop)
    process_projection_events_loop.add_argument(
        "--bootstrap-rebuild",
        action="store_true",
        help="Before listening for new projection events, enqueue missing GraphFact batches from existing PostgreSQL data.",
    )
    process_projection_events_loop.add_argument(
        "--bootstrap-rebuild-limit",
        type=int,
        default=None,
        help="Maximum source rows scanned by the startup bootstrap rebuild. Defaults to GRAPH_BOOTSTRAP_REBUILD_LIMIT.",
    )


def _add_experience_commands(subparsers) -> None:
    propose_experience = subparsers.add_parser("propose-action-experience", help="Persist internal next-action proposals from Neo4j/GDS experience.")
    _add_action_experience_arguments(propose_experience)
    propose_experience_loop = subparsers.add_parser("propose-action-experience-loop", help="Continuously persist internal next-action proposals from Neo4j/GDS experience.")
    _add_action_experience_arguments(propose_experience_loop)
    propose_experience_loop.add_argument("--max-iterations", type=int, default=None)
    propose_experience_loop.add_argument("--idle-exit-after", type=int, default=None)
    propose_experience_loop.add_argument("--poll-seconds", type=float, default=None)


def _add_surface_commands(subparsers) -> None:
    surface_components = subparsers.add_parser(
        "surface-components",
        help="Display read-only Surface Map component analytics from Neo4j/GDS.",
    )
    _add_surface_component_report_arguments(surface_components)
    surface_components.add_argument("--json", action="store_true", dest="json_output")

    surface_components_materialize = subparsers.add_parser(
        "surface-components-materialize",
        help="Run Surface Map component analytics once and persist a PostgreSQL read model.",
    )
    _add_surface_component_report_arguments(surface_components_materialize)
    surface_components_materialize.add_argument("--json", action="store_true", dest="json_output")

    surface_components_materialized = subparsers.add_parser(
        "surface-components-materialized",
        help="Read the latest persisted Surface Map component analytics from PostgreSQL without running GDS.",
    )
    surface_components_materialized.add_argument("--program-id", required=True)
    surface_components_materialized.add_argument("--snapshot-id", required=True)
    surface_components_materialized.add_argument("--previous-snapshot-id", default=None)
    surface_components_materialized.add_argument("--json", action="store_true", dest="json_output")

    process_surface_analysis_events = subparsers.add_parser(
        "process-surface-analysis-events",
        help="Process pending Surface Component analysis materialization events.",
    )
    process_surface_analysis_events.add_argument("--program-id", default=None)
    process_surface_analysis_events.add_argument("--limit", type=int, default=None)

    process_surface_analysis_events_loop = subparsers.add_parser(
        "process-surface-analysis-events-loop",
        help="Continuously process pending Surface Component analysis materialization events.",
    )
    process_surface_analysis_events_loop.add_argument("--program-id", default=None)
    process_surface_analysis_events_loop.add_argument("--max-events", type=int, default=None)
    process_surface_analysis_events_loop.add_argument("--idle-exit-after", type=int, default=None)
    process_surface_analysis_events_loop.add_argument("--poll-seconds", type=float, default=None)


def _add_maintenance_commands(subparsers) -> None:
    retry = subparsers.add_parser("retry", help="Reset failed/dead durable projection rows back to pending without rebuilding source data.")
    retry.add_argument("--program-id", default=None)
    retry.add_argument("--limit", type=int, default=None)
    retry.add_argument(
        "--queue",
        action="append",
        choices=sorted(GRAPH_PROJECTOR_RETRY_QUEUES),
        dest="queues",
        help="Retry one durable queue; repeat to select several. Defaults to both queues.",
    )
    retry.add_argument(
        "--status",
        action="append",
        choices=sorted(GRAPH_PROJECTOR_RETRY_STATUSES),
        dest="statuses",
        help="Retry one status; repeat to select several. Defaults to failed and dead. Locked retries affect stale locks only.",
    )

    rebuild = subparsers.add_parser("rebuild", help="Requeue GraphFactBatch rows from canonical PostgreSQL data.")
    rebuild.add_argument("--limit", type=int, default=None)
    rebuild.add_argument("--program-id", default=None)
    rebuild.add_argument(
        "--source",
        action="append",
        choices=sorted(GRAPH_REBUILD_SOURCES),
        dest="sources",
        help="Limit rebuild to one source; repeat to select several sources.",
    )


def _add_queue_threshold_arguments(command) -> None:
    command.add_argument("--max-pending-projection-events", type=int, default=0)
    command.add_argument("--max-pending-graph-fact-batches", type=int, default=0)
    command.add_argument("--max-failed-projection-events", type=int, default=0)
    command.add_argument("--max-failed-graph-fact-batches", type=int, default=0)
    command.add_argument("--max-dead-projection-events", type=int, default=0)
    command.add_argument("--max-dead-graph-fact-batches", type=int, default=0)
    command.add_argument("--max-pending-surface-analysis-events", type=int, default=0)
    command.add_argument("--max-failed-surface-analysis-events", type=int, default=0)
    command.add_argument("--max-dead-surface-analysis-events", type=int, default=0)


def _add_limit_program_arguments(command) -> None:
    command.add_argument("--limit", type=int, default=None)
    command.add_argument("--program-id", default=None)


def _add_enqueue_loop_arguments(command) -> None:
    _add_limit_program_arguments(command)
    command.add_argument("--max-iterations", type=int, default=None)
    command.add_argument("--idle-exit-after", type=int, default=None)
    command.add_argument("--poll-seconds", type=float, default=None)


def _add_action_experience_arguments(command) -> None:
    command.add_argument("--limit", type=int, default=None)
    command.add_argument("--program-id", default=None)
    command.add_argument("--candidate-limit", type=int, default=None)
    command.add_argument("--similarity-cutoff", type=float, default=None)


def _add_surface_component_report_arguments(command) -> None:
    command.add_argument("--program-id", required=True)
    command.add_argument("--snapshot-id", required=True)
    command.add_argument("--previous-snapshot-id", default=None)
    command.add_argument("--limit", type=int, default=10)
    command.add_argument("--candidate-limit", type=int, default=10)
    command.add_argument("--component-limit", type=int, default=10)
    command.add_argument("--similarity-cutoff", type=float, default=0.03)
    command.add_argument("--no-action-candidates", action="store_true")
