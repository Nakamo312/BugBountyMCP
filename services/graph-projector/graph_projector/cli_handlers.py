from __future__ import annotations

from .cli_batch_commands import (
    apply_loop,
    apply_one,
    enqueue_action_outcomes,
    enqueue_action_outcomes_loop,
    enqueue_http_observations,
    enqueue_http_observations_loop,
    enqueue_javascript_references,
    enqueue_javascript_references_loop,
    enqueue_raw_artifacts,
    enqueue_raw_artifacts_loop,
    process_projection_events,
    process_projection_events_loop,
)
from .cli_maintenance_commands import rebuild, retry
from .cli_operational_commands import check_config, diagnostics, health, status
from .cli_surface_commands import (
    process_surface_analysis_events,
    process_surface_analysis_events_loop,
    propose_action_experience,
    propose_action_experience_loop,
    surface_components,
    surface_components_materialize,
    surface_components_materialized,
)


class GraphProjectorCli:
    COMMAND_HANDLERS = {
        "check-config": check_config,
        "status": status,
        "diagnostics": diagnostics,
        "health": health,
        "apply-one": apply_one,
        "apply-loop": apply_loop,
        "enqueue-raw-artifacts": enqueue_raw_artifacts,
        "enqueue-raw-artifacts-loop": enqueue_raw_artifacts_loop,
        "enqueue-http-observations": enqueue_http_observations,
        "enqueue-http-observations-loop": enqueue_http_observations_loop,
        "enqueue-javascript-references": enqueue_javascript_references,
        "enqueue-javascript-references-loop": enqueue_javascript_references_loop,
        "enqueue-action-outcomes": enqueue_action_outcomes,
        "enqueue-action-outcomes-loop": enqueue_action_outcomes_loop,
        "process-projection-events": process_projection_events,
        "process-projection-events-loop": process_projection_events_loop,
        "propose-action-experience": propose_action_experience,
        "propose-action-experience-loop": propose_action_experience_loop,
        "surface-components": surface_components,
        "surface-components-materialize": surface_components_materialize,
        "surface-components-materialized": surface_components_materialized,
        "process-surface-analysis-events": process_surface_analysis_events,
        "process-surface-analysis-events-loop": process_surface_analysis_events_loop,
        "retry": retry,
        "rebuild": rebuild
    }

    def run(self, args) -> int:
        handler = self.COMMAND_HANDLERS.get(args.command)
        if handler is None:
            return 2
        return handler(args)
