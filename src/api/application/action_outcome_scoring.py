"""Action outcome utility scoring policy."""
from __future__ import annotations

from api.application.contracts import (
    ActionOutcomeMeasures,
    ActionOutcomeScore,
    ExecutionStatus,
    TerminalOutcome,
)


class ActionOutcomeScoreCalculator:
    """Deterministic first-pass utility score for one action outcome.

    This score is intentionally only a raw telemetry utility. Projection novelty
    counters remain stored for diagnostics, but they are not used as reward: raw
    counts are a poor proxy for whether the system became better at choosing the
    next action. Candidate ranking is handled later by the experience graph over
    state/action pairs and feedback.
    """

    SCORE_VERSION = "action-outcome-raw-utility.v2"

    @classmethod
    def calculate(
        cls,
        *,
        measures: ActionOutcomeMeasures,
        status: ExecutionStatus | str,
        terminal_outcome: TerminalOutcome | str | None,
    ) -> ActionOutcomeScore:
        status_value = status.value if isinstance(status, ExecutionStatus) else str(status)
        terminal_value = (
            terminal_outcome.value
            if isinstance(terminal_outcome, TerminalOutcome)
            else (str(terminal_outcome) if terminal_outcome is not None else None)
        )

        # Saturated units keep volume from becoming reward. One thousand
        # duplicate observations should not beat one cheap action that later
        # changes the proposal distribution. Projection-level novelty counters
        # are persisted as telemetry, but not fed into this score.
        raw_artifact_units = _saturated_units(measures.raw_artifact_count, weight=0.75)
        observation_units = _saturated_units(measures.http_observation_count, weight=1.0)
        javascript_units = _saturated_units(measures.javascript_reference_count, weight=1.25)
        exposure_units = _saturated_units(measures.observed_hosts_count, weight=0.6)
        exposure_units += _saturated_units(measures.observed_services_count, weight=0.6)
        exposure_units += _saturated_units(measures.observed_endpoints_count, weight=0.8)

        information_units = raw_artifact_units + observation_units + javascript_units + exposure_units
        duration_seconds = float(measures.duration_ms or 0) / 1000.0
        duration_penalty = duration_seconds / 60.0
        error_penalty = float(measures.error_count) * 5.0
        terminal_penalty = 10.0 if terminal_value == TerminalOutcome.TOOL_FAILED.value else 0.0
        nonterminal_penalty = 2.0 if status_value not in {
            ExecutionStatus.COMPLETED.value,
            ExecutionStatus.FAILED.value,
            ExecutionStatus.DEAD.value,
            ExecutionStatus.CANCELLED.value,
        } else 0.0
        cost_units = 1.0 + duration_penalty + error_penalty + terminal_penalty + nonterminal_penalty
        score = max(0.0, round(information_units / cost_units, 6))
        return ActionOutcomeScore(
            information_gain_score=score,
            score_version=cls.SCORE_VERSION,
            score_breakdown={
                "raw_artifact_units": raw_artifact_units,
                "observation_units": observation_units,
                "javascript_units": javascript_units,
                "exposure_units": exposure_units,
                "diagnostic_projection_novelty": {
                    "new_hosts_count": measures.new_hosts_count,
                    "new_services_count": measures.new_services_count,
                    "new_endpoints_count": measures.new_endpoints_count,
                    "new_surface_nodes_count": measures.new_surface_nodes_count,
                    "new_surface_edges_count": measures.new_surface_edges_count,
                    "new_surface_clusters_count": measures.new_surface_clusters_count,
                    "new_surface_deltas_count": measures.new_surface_deltas_count,
                    "new_graph_facts_count": measures.new_graph_facts_count,
                    "new_search_documents_count": measures.new_search_documents_count,
                    "scoring_role": "telemetry_only",
                },
                "duration_penalty": duration_penalty,
                "error_penalty": error_penalty,
                "terminal_penalty": terminal_penalty,
                "nonterminal_penalty": nonterminal_penalty,
                "information_units": information_units,
                "cost_units": cost_units,
            },
        )


def _saturated_units(value: int | None, *, weight: float) -> float:
    count = max(0, int(value or 0))
    if count == 0:
        return 0.0
    # Concave growth: each extra raw row matters less than the previous one.
    return round((count ** 0.5) * weight, 6)
