"""Row/value mappers for action outcome records."""
from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from api.application.contracts import (
    ActionOutcomeDraft,
    ActionOutcomeMeasures,
    ActionOutcomeRecord,
    ActionOutcomeScore,
    ExecutionStatus,
    TerminalOutcome,
)


def duration_ms(started_at: datetime | None, finished_at: datetime | None) -> int | None:
    if started_at is None or finished_at is None:
        return None
    return max(0, int((finished_at - started_at).total_seconds() * 1000))


def target_count(row: Mapping[str, Any]) -> int | None:
    if row.get("target_count") is not None:
        return int(row["target_count"])
    payload = row.get("run_payload") or {}
    if isinstance(payload, Mapping):
        targets = payload.get("targets")
        if isinstance(targets, list):
            return len(targets)
        target = payload.get("target")
        if target:
            return 1
    return None


def optional_terminal_outcome(value: Any) -> TerminalOutcome | None:
    return TerminalOutcome(value) if value is not None else None


def draft_from_run_context(
    *,
    row: Mapping[str, Any],
    measures: ActionOutcomeMeasures,
) -> ActionOutcomeDraft:
    return ActionOutcomeDraft(
        row=dict(row),
        outcome_id=row.get("outcome_id") or uuid.uuid4(),
        measures=measures,
        status=ExecutionStatus(row["status"]),
        terminal_outcome=optional_terminal_outcome(row.get("terminal_outcome")),
    )


def values_from_run_context(
    *,
    row: Mapping[str, Any],
    outcome_id: uuid.UUID,
    measures: ActionOutcomeMeasures,
    score: ActionOutcomeScore,
    now: datetime,
) -> dict[str, Any]:
    return {
        "id": outcome_id,
        "program_id": row["program_id"],
        "campaign_id": row.get("campaign_id"),
        "action_id": row["action_id"],
        "job_id": row["job_id"],
        "run_id": row["run_id"],
        "capability_id": row["capability_id"],
        "profile_id": row["profile_id"],
        "node_id": row.get("node_id"),
        "event_name": row.get("event_name"),
        "correlation_id": row.get("correlation_id"),
        "status": row["status"],
        "terminal_outcome": row.get("terminal_outcome"),
        "attempt": int(row["attempt"]),
        "target_count": target_count(row),
        "started_at": row.get("started_at"),
        "finished_at": row.get("finished_at"),
        "duration_ms": measures.duration_ms,
        "error_count": measures.error_count,
        "error_message": row.get("error"),
        "raw_artifact_count": measures.raw_artifact_count,
        "raw_artifact_bytes": measures.raw_artifact_bytes,
        "observed_hosts_count": measures.observed_hosts_count,
        "observed_services_count": measures.observed_services_count,
        "observed_endpoints_count": measures.observed_endpoints_count,
        "http_observation_count": measures.http_observation_count,
        "javascript_reference_count": measures.javascript_reference_count,
        "new_hosts_count": measures.new_hosts_count,
        "new_services_count": measures.new_services_count,
        "new_endpoints_count": measures.new_endpoints_count,
        "new_surface_nodes_count": measures.new_surface_nodes_count,
        "new_surface_edges_count": measures.new_surface_edges_count,
        "new_surface_clusters_count": measures.new_surface_clusters_count,
        "new_surface_deltas_count": measures.new_surface_deltas_count,
        "new_graph_facts_count": measures.new_graph_facts_count,
        "new_search_documents_count": measures.new_search_documents_count,
        "information_gain_score": score.information_gain_score,
        "score_version": score.score_version,
        "score_breakdown": score.score_breakdown,
        "created_at": now,
        "updated_at": now,
    }


def action_outcome_record_from_row(values: Mapping[str, Any]) -> ActionOutcomeRecord:
    measures = ActionOutcomeMeasures(
        raw_artifact_count=int(values.get("raw_artifact_count") or 0),
        raw_artifact_bytes=int(values.get("raw_artifact_bytes") or 0),
        observed_hosts_count=int(values.get("observed_hosts_count") or 0),
        observed_services_count=int(values.get("observed_services_count") or 0),
        observed_endpoints_count=int(values.get("observed_endpoints_count") or 0),
        http_observation_count=int(values.get("http_observation_count") or 0),
        javascript_reference_count=int(values.get("javascript_reference_count") or 0),
        new_hosts_count=values.get("new_hosts_count"),
        new_services_count=values.get("new_services_count"),
        new_endpoints_count=values.get("new_endpoints_count"),
        new_surface_nodes_count=values.get("new_surface_nodes_count"),
        new_surface_edges_count=values.get("new_surface_edges_count"),
        new_surface_clusters_count=values.get("new_surface_clusters_count"),
        new_surface_deltas_count=values.get("new_surface_deltas_count"),
        new_graph_facts_count=values.get("new_graph_facts_count"),
        new_search_documents_count=values.get("new_search_documents_count"),
        duration_ms=values.get("duration_ms"),
        error_count=int(values.get("error_count") or 0),
    )
    score = ActionOutcomeScore(
        information_gain_score=float(values.get("information_gain_score") or 0.0),
        score_version=values["score_version"],
        score_breakdown=dict(values.get("score_breakdown") or {}),
    )
    return action_outcome_record_from_values(
        values=values,
        measures=measures,
        score=score,
    )


def action_outcome_record_from_values(
    *,
    values: Mapping[str, Any],
    measures: ActionOutcomeMeasures,
    score: ActionOutcomeScore,
) -> ActionOutcomeRecord:
    return ActionOutcomeRecord(
        outcome_id=values["id"],
        program_id=values["program_id"],
        campaign_id=values.get("campaign_id"),
        action_id=values["action_id"],
        job_id=values["job_id"],
        run_id=values["run_id"],
        capability_id=values["capability_id"],
        profile_id=values["profile_id"],
        node_id=values.get("node_id"),
        event_name=values.get("event_name"),
        correlation_id=values.get("correlation_id"),
        status=ExecutionStatus(values["status"]),
        terminal_outcome=optional_terminal_outcome(values.get("terminal_outcome")),
        attempt=int(values["attempt"]),
        target_count=values.get("target_count"),
        started_at=values.get("started_at"),
        finished_at=values.get("finished_at"),
        duration_ms=values.get("duration_ms"),
        error_count=int(values.get("error_count") or 0),
        error_message=values.get("error_message"),
        measures=measures,
        score=score,
        manual_interest=values.get("manual_interest"),
        manual_stop=values.get("manual_stop"),
        continued_by_followup=values.get("continued_by_followup"),
        report_created=values.get("report_created"),
        triage_outcome=values.get("triage_outcome"),
        created_at=values["created_at"],
        updated_at=values["updated_at"],
    )
