"""Action and outcome read helpers for dashboard workbench projections.

This module owns SQL row loading and small DTO helpers for persisted action
history. It does not build graph lenses, submit actions, execute tools, read raw
artifact bodies, or perform policy decisions.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import bindparam, desc, or_, select

from api.application.workbench import WorkbenchActionAffordance
from api.infrastructure.adapters.orm import (
    action_outcome_feedback_events,
    action_outcomes,
    action_request_targets,
    action_requests,
    approval_decisions,
    approval_requests,
    jobs,
    policy_decisions,
    raw_artifacts,
    runs,
)

_ACTION_COLUMNS = (
    action_requests.c.id.label("action_id"),
    action_requests.c.catalog_entry_id,
    action_requests.c.capability_id,
    action_requests.c.profile_id,
    action_requests.c.requested_by,
    action_requests.c.campaign_id,
    action_requests.c.correlation_id,
    action_requests.c.metadata,
    action_requests.c.status,
    action_requests.c.request,
    action_requests.c.created_at,
    action_requests.c.updated_at,
)

_TARGET_COLUMNS = (
    action_request_targets.c.id.label("target_id"),
    action_request_targets.c.action_id,
    action_request_targets.c.target,
    action_request_targets.c.position,
    action_request_targets.c.status.label("target_status"),
    action_request_targets.c.created_at,
)

_POLICY_COLUMNS = (
    policy_decisions.c.id.label("policy_decision_id"),
    policy_decisions.c.action_id,
    policy_decisions.c.status,
    policy_decisions.c.reasons,
    policy_decisions.c.allowed_targets,
    policy_decisions.c.blocked_targets,
    policy_decisions.c.safety_level,
    policy_decisions.c.metadata,
    policy_decisions.c.catalog_hash,
    policy_decisions.c.created_at,
)

_APPROVAL_REQUEST_COLUMNS = (
    approval_requests.c.id.label("approval_request_id"),
    approval_requests.c.action_id,
    approval_requests.c.policy_decision_id,
    approval_requests.c.status,
    approval_requests.c.reason,
    approval_requests.c.requested_by,
    approval_requests.c.created_at,
    approval_requests.c.decided_at,
)

_APPROVAL_DECISION_COLUMNS = (
    approval_decisions.c.id.label("approval_decision_id"),
    approval_decisions.c.approval_request_id,
    approval_decisions.c.action_id,
    approval_decisions.c.decision,
    approval_decisions.c.decided_by,
    approval_decisions.c.reason,
    approval_decisions.c.metadata,
    approval_decisions.c.created_at,
)

_JOB_COLUMNS = (
    jobs.c.id.label("job_id"),
    jobs.c.action_id,
    jobs.c.program_id,
    jobs.c.capability_id,
    jobs.c.profile_id,
    jobs.c.status,
    jobs.c.correlation_id,
    jobs.c.campaign_id,
    jobs.c.created_at,
    jobs.c.updated_at,
)

_RUN_COLUMNS = (
    runs.c.id.label("run_id"),
    runs.c.job_id,
    runs.c.program_id,
    runs.c.node_id,
    runs.c.event_name,
    runs.c.execution_mode,
    runs.c.status,
    runs.c.attempt,
    runs.c.target_count,
    runs.c.terminal_outcome,
    runs.c.needs_reconcile,
    runs.c.retry_reason,
    runs.c.error,
    runs.c.created_at,
    runs.c.updated_at,
    runs.c.started_at,
    runs.c.finished_at,
)

_FEEDBACK_COLUMNS = (
    action_outcome_feedback_events.c.id.label("feedback_id"),
    action_outcome_feedback_events.c.outcome_id,
    action_outcome_feedback_events.c.program_id,
    action_outcome_feedback_events.c.campaign_id,
    action_outcome_feedback_events.c.action_id,
    action_outcome_feedback_events.c.job_id,
    action_outcome_feedback_events.c.run_id,
    action_outcome_feedback_events.c.manual_interest,
    action_outcome_feedback_events.c.manual_stop,
    action_outcome_feedback_events.c.continued_by_followup,
    action_outcome_feedback_events.c.report_created,
    action_outcome_feedback_events.c.triage_outcome,
    action_outcome_feedback_events.c.actor,
    action_outcome_feedback_events.c.source,
    action_outcome_feedback_events.c.reason,
    action_outcome_feedback_events.c.confidence,
    action_outcome_feedback_events.c.created_at,
)

_OUTCOME_COLUMNS = (
    action_outcomes.c.id.label("outcome_id"),
    action_outcomes.c.program_id,
    action_outcomes.c.campaign_id,
    action_outcomes.c.action_id,
    action_outcomes.c.job_id,
    action_outcomes.c.run_id,
    action_outcomes.c.capability_id,
    action_outcomes.c.profile_id,
    action_outcomes.c.node_id,
    action_outcomes.c.event_name,
    action_outcomes.c.status,
    action_outcomes.c.terminal_outcome,
    action_outcomes.c.attempt,
    action_outcomes.c.duration_ms,
    action_outcomes.c.error_count,
    action_outcomes.c.raw_artifact_count,
    action_outcomes.c.observed_hosts_count,
    action_outcomes.c.observed_services_count,
    action_outcomes.c.observed_endpoints_count,
    action_outcomes.c.http_observation_count,
    action_outcomes.c.javascript_reference_count,
    action_outcomes.c.new_hosts_count,
    action_outcomes.c.new_services_count,
    action_outcomes.c.new_endpoints_count,
    action_outcomes.c.new_surface_nodes_count,
    action_outcomes.c.new_surface_edges_count,
    action_outcomes.c.new_surface_clusters_count,
    action_outcomes.c.new_surface_deltas_count,
    action_outcomes.c.new_graph_facts_count,
    action_outcomes.c.new_search_documents_count,
    action_outcomes.c.manual_interest,
    action_outcomes.c.manual_stop,
    action_outcomes.c.continued_by_followup,
    action_outcomes.c.report_created,
    action_outcomes.c.triage_outcome,
    action_outcomes.c.information_gain_score,
    action_outcomes.c.score_breakdown,
    action_outcomes.c.created_at,
    action_outcomes.c.finished_at,
)



async def _recent_action_requests_for_program(session: Any, program_id: UUID, *, limit: int) -> list[Mapping[str, Any]]:
    statement = (
        select(*_ACTION_COLUMNS)
        .where(action_requests.c.program_id == bindparam("program_id"))
        .order_by(desc(action_requests.c.created_at), desc(action_requests.c.id))
        .limit(max(limit, 1))
    )
    result = await session.execute(statement, {"program_id": program_id})
    return list(result.mappings().all())


async def _targets_for_actions(session: Any, action_ids: list[UUID], *, limit: int) -> list[Mapping[str, Any]]:
    if not action_ids:
        return []
    statement = (
        select(*_TARGET_COLUMNS)
        .where(action_request_targets.c.action_id.in_(bindparam("action_ids", expanding=True)))
        .order_by(action_request_targets.c.action_id.asc(), action_request_targets.c.position.asc())
        .limit(max(limit, 1))
    )
    result = await session.execute(statement, {"action_ids": action_ids})
    return list(result.mappings().all())


async def _policy_decisions_for_actions(session: Any, action_ids: list[UUID], *, limit: int) -> list[Mapping[str, Any]]:
    if not action_ids:
        return []
    statement = (
        select(*_POLICY_COLUMNS)
        .where(policy_decisions.c.action_id.in_(bindparam("action_ids", expanding=True)))
        .order_by(desc(policy_decisions.c.created_at), desc(policy_decisions.c.id))
        .limit(max(limit, 1))
    )
    result = await session.execute(statement, {"action_ids": action_ids})
    return list(result.mappings().all())


async def _approval_requests_for_actions(session: Any, action_ids: list[UUID], *, limit: int) -> list[Mapping[str, Any]]:
    if not action_ids:
        return []
    statement = (
        select(*_APPROVAL_REQUEST_COLUMNS)
        .where(approval_requests.c.action_id.in_(bindparam("action_ids", expanding=True)))
        .order_by(desc(approval_requests.c.created_at), desc(approval_requests.c.id))
        .limit(max(limit, 1))
    )
    result = await session.execute(statement, {"action_ids": action_ids})
    return list(result.mappings().all())


async def _approval_decisions_for_actions(session: Any, action_ids: list[UUID], *, limit: int) -> list[Mapping[str, Any]]:
    if not action_ids:
        return []
    statement = (
        select(*_APPROVAL_DECISION_COLUMNS)
        .where(approval_decisions.c.action_id.in_(bindparam("action_ids", expanding=True)))
        .order_by(desc(approval_decisions.c.created_at), desc(approval_decisions.c.id))
        .limit(max(limit, 1))
    )
    result = await session.execute(statement, {"action_ids": action_ids})
    return list(result.mappings().all())


async def _jobs_for_actions(session: Any, action_ids: list[UUID], *, limit: int) -> list[Mapping[str, Any]]:
    if not action_ids:
        return []
    statement = (
        select(*_JOB_COLUMNS)
        .where(jobs.c.action_id.in_(bindparam("action_ids", expanding=True)))
        .order_by(desc(jobs.c.created_at), desc(jobs.c.id))
        .limit(max(limit, 1))
    )
    result = await session.execute(statement, {"action_ids": action_ids})
    return list(result.mappings().all())


async def _runs_for_jobs(session: Any, job_ids: list[UUID], *, limit: int) -> list[Mapping[str, Any]]:
    if not job_ids:
        return []
    statement = (
        select(*_RUN_COLUMNS)
        .where(runs.c.job_id.in_(bindparam("job_ids", expanding=True)))
        .order_by(desc(runs.c.created_at), desc(runs.c.id))
        .limit(max(limit, 1))
    )
    result = await session.execute(statement, {"job_ids": job_ids})
    return list(result.mappings().all())


async def _outcomes_for_actions(
    session: Any,
    program_id: UUID,
    action_ids: list[UUID],
    *,
    limit: int,
) -> list[Mapping[str, Any]]:
    if not action_ids:
        return []
    statement = (
        select(*_OUTCOME_COLUMNS)
        .where(action_outcomes.c.program_id == bindparam("program_id"))
        .where(action_outcomes.c.action_id.in_(bindparam("action_ids", expanding=True)))
        .order_by(desc(action_outcomes.c.created_at), desc(action_outcomes.c.id))
        .limit(max(limit, 1))
    )
    result = await session.execute(statement, {"program_id": program_id, "action_ids": action_ids})
    return list(result.mappings().all())


async def _feedback_for_actions(
    session: Any,
    program_id: UUID,
    action_ids: list[UUID],
    *,
    limit: int,
) -> list[Mapping[str, Any]]:
    if not action_ids:
        return []
    statement = (
        select(*_FEEDBACK_COLUMNS)
        .where(action_outcome_feedback_events.c.program_id == bindparam("program_id"))
        .where(action_outcome_feedback_events.c.action_id.in_(bindparam("action_ids", expanding=True)))
        .order_by(desc(action_outcome_feedback_events.c.created_at), desc(action_outcome_feedback_events.c.id))
        .limit(max(limit, 1))
    )
    result = await session.execute(statement, {"program_id": program_id, "action_ids": action_ids})
    return list(result.mappings().all())


async def _actions_for_entity(
    session: Any,
    program_id: UUID,
    targets: list[str],
    *,
    limit: int,
) -> list[Mapping[str, Any]]:
    if not targets:
        return []
    statement = (
        select(
            action_requests.c.id.label("action_id"),
            action_requests.c.catalog_entry_id,
            action_requests.c.capability_id,
            action_requests.c.profile_id,
            action_requests.c.requested_by,
            action_requests.c.campaign_id,
            action_requests.c.correlation_id,
            action_requests.c.metadata,
            action_requests.c.status,
            action_requests.c.request,
            action_requests.c.created_at,
            action_request_targets.c.target,
            action_request_targets.c.status.label("target_status"),
        )
        .select_from(action_requests.join(action_request_targets, action_request_targets.c.action_id == action_requests.c.id))
        .where(action_requests.c.program_id == bindparam("program_id"))
        .where(action_request_targets.c.target.in_(bindparam("targets", expanding=True)))
        .order_by(desc(action_requests.c.created_at), desc(action_requests.c.id))
        .limit(max(limit, 1) * 4)
    )
    result = await session.execute(statement, {"program_id": program_id, "targets": targets})
    return _dedupe_action_rows(result.mappings().all(), limit=limit)


async def _outcomes_for_entity(
    session: Any,
    program_id: UUID,
    targets: list[str],
    action_ids: list[UUID],
    *,
    limit: int,
) -> list[Mapping[str, Any]]:
    conditions = []
    parameters: dict[str, object] = {"program_id": program_id}
    if action_ids:
        conditions.append(action_outcomes.c.action_id.in_(bindparam("action_ids", expanding=True)))
        parameters["action_ids"] = action_ids
    if targets:
        conditions.append(action_outcomes.c.node_id.in_(bindparam("targets", expanding=True)))
        parameters["targets"] = targets
    if not conditions:
        return []

    statement = (
        select(*_OUTCOME_COLUMNS)
        .where(action_outcomes.c.program_id == bindparam("program_id"))
        .where(or_(*conditions))
        .order_by(desc(action_outcomes.c.created_at), desc(action_outcomes.c.id))
        .limit(max(limit, 1))
    )
    result = await session.execute(statement, parameters)
    return list(result.mappings().all())


async def _recent_outcomes_for_program(session: Any, program_id: UUID, *, limit: int) -> list[Mapping[str, Any]]:
    statement = (
        select(*_OUTCOME_COLUMNS)
        .where(action_outcomes.c.program_id == bindparam("program_id"))
        .order_by(desc(action_outcomes.c.created_at), desc(action_outcomes.c.id))
        .limit(max(limit, 1))
    )
    result = await session.execute(statement, {"program_id": program_id})
    return list(result.mappings().all())


async def _recent_action_targets_for_program(session: Any, program_id: UUID, *, limit: int) -> list[Mapping[str, Any]]:
    statement = (
        select(
            action_requests.c.id.label("action_id"),
            action_requests.c.catalog_entry_id,
            action_requests.c.capability_id,
            action_requests.c.profile_id,
            action_requests.c.requested_by,
            action_requests.c.campaign_id,
            action_requests.c.correlation_id,
            action_requests.c.metadata,
            action_requests.c.status,
            action_requests.c.request,
            action_requests.c.created_at,
            action_request_targets.c.target,
            action_request_targets.c.status.label("target_status"),
        )
        .select_from(action_requests.join(action_request_targets, action_request_targets.c.action_id == action_requests.c.id))
        .where(action_requests.c.program_id == bindparam("program_id"))
        .order_by(desc(action_requests.c.created_at), desc(action_requests.c.id), action_request_targets.c.position.asc())
        .limit(max(limit, 1))
    )
    result = await session.execute(statement, {"program_id": program_id})
    return list(result.mappings().all())


async def _artifacts_for_outcomes(
    session: Any,
    run_ids: list[UUID],
    *,
    program_id: UUID | None = None,
    limit: int,
) -> list[Mapping[str, Any]]:
    if not run_ids:
        return []
    statement = select(
        raw_artifacts.c.id.label("artifact_id"),
        raw_artifacts.c.run_id,
        raw_artifacts.c.job_id,
        raw_artifacts.c.node_id,
        raw_artifacts.c.event_name,
        raw_artifacts.c.artifact_type,
        raw_artifacts.c.sha256,
        raw_artifacts.c.size_bytes,
        raw_artifacts.c.storage_size_bytes,
        raw_artifacts.c.content_encoding,
        raw_artifacts.c.retention_class,
        raw_artifacts.c.raw_safe_for_llm,
        raw_artifacts.c.sanitized_safe_for_llm,
        raw_artifacts.c.parser_name,
        raw_artifacts.c.parser_version,
        raw_artifacts.c.created_at,
    ).where(raw_artifacts.c.run_id.in_(bindparam("run_ids", expanding=True)))
    parameters: dict[str, object] = {"run_ids": run_ids}
    if program_id is not None:
        statement = statement.where(raw_artifacts.c.program_id == bindparam("artifact_program_id"))
        parameters["artifact_program_id"] = program_id
    statement = statement.order_by(desc(raw_artifacts.c.created_at), desc(raw_artifacts.c.id)).limit(max(limit, 1))
    result = await session.execute(statement, parameters)
    return list(result.mappings().all())


def _dedupe_action_rows(rows: list[Mapping[str, Any]], *, limit: int) -> list[Mapping[str, Any]]:
    selected: list[Mapping[str, Any]] = []
    seen: set[UUID] = set()
    for row in rows:
        action_id = row["action_id"]
        if action_id in seen:
            continue
        seen.add(action_id)
        selected.append(row)
        if len(selected) >= limit:
            break
    return selected


def _action_affordance(row: Mapping[str, Any], outcomes: list[Mapping[str, Any]]) -> WorkbenchActionAffordance:
    request = _dict(row.get("request"))
    status = str(row["status"])
    target_status = str(row.get("target_status") or "")
    enabled = status in {"allowed", "queued"} and target_status != "blocked"
    return WorkbenchActionAffordance(
        catalog_id=_catalog_id(row),
        label=f"{row['capability_id']} / {row['profile_id']}",
        profile=str(row["profile_id"]),
        prefilled_options=_dict(request.get("options")),
        enabled=enabled,
        disabled_reasons=_action_disabled_reasons(status, target_status),
        policy_preview={
            "action_id": str(row["action_id"]),
            "status": status,
            "target_status": target_status or None,
            "requested_by": row.get("requested_by"),
            "campaign_id": _str_or_none(row.get("campaign_id")),
            "correlation_id": _str_or_none(row.get("correlation_id")),
        },
        budget_preview=_dict(request.get("budget")),
        expected_delta=_expected_delta_from_outcomes(outcomes),
        prior_outcomes=[_outcome_summary(outcome) for outcome in outcomes[:5]],
    )


def _action_summary(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "action_id": str(row["action_id"]),
        "catalog_id": _catalog_id(row),
        "capability_id": row.get("capability_id"),
        "profile_id": row.get("profile_id"),
        "status": row.get("status"),
        "target": row.get("target"),
        "target_status": row.get("target_status"),
        "created_at": _iso(row.get("created_at")),
    }


def _outcome_summary(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "outcome_id": str(row["outcome_id"]),
        "action_id": str(row["action_id"]),
        "run_id": str(row["run_id"]),
        "capability_id": row.get("capability_id"),
        "profile_id": row.get("profile_id"),
        "status": row.get("status"),
        "terminal_outcome": row.get("terminal_outcome"),
        "information_gain_score": float(row.get("information_gain_score") or 0.0),
        "new_surface_nodes_count": row.get("new_surface_nodes_count"),
        "new_surface_edges_count": row.get("new_surface_edges_count"),
        "new_surface_deltas_count": row.get("new_surface_deltas_count"),
        "created_at": _iso(row.get("created_at")),
        "finished_at": _iso(row.get("finished_at")),
    }


def _outcome_fragment(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "kind": "action_outcome",
        "id": str(row["outcome_id"]),
        "action_id": str(row["action_id"]),
        "run_id": str(row["run_id"]),
        "capability_id": row.get("capability_id"),
        "profile_id": row.get("profile_id"),
        "node_id": row.get("node_id"),
        "event_name": row.get("event_name"),
        "status": row.get("status"),
        "terminal_outcome": row.get("terminal_outcome"),
        "attempt": row.get("attempt"),
        "duration_ms": row.get("duration_ms"),
        "error_count": row.get("error_count"),
        "observations": {
            "raw_artifacts": row.get("raw_artifact_count"),
            "hosts": row.get("observed_hosts_count"),
            "services": row.get("observed_services_count"),
            "endpoints": row.get("observed_endpoints_count"),
            "http": row.get("http_observation_count"),
            "javascript_refs": row.get("javascript_reference_count"),
        },
        "delta": {
            "hosts": row.get("new_hosts_count"),
            "services": row.get("new_services_count"),
            "endpoints": row.get("new_endpoints_count"),
            "surface_nodes": row.get("new_surface_nodes_count"),
            "surface_edges": row.get("new_surface_edges_count"),
            "surface_clusters": row.get("new_surface_clusters_count"),
            "surface_deltas": row.get("new_surface_deltas_count"),
            "graph_facts": row.get("new_graph_facts_count"),
            "search_documents": row.get("new_search_documents_count"),
        },
        "feedback": {
            "manual_interest": row.get("manual_interest"),
            "manual_stop": row.get("manual_stop"),
            "continued_by_followup": row.get("continued_by_followup"),
            "report_created": row.get("report_created"),
            "triage_outcome": row.get("triage_outcome"),
        },
        "score": {
            "information_gain": float(row.get("information_gain_score") or 0.0),
            "breakdown": _dict(row.get("score_breakdown")),
        },
        "created_at": _iso(row.get("created_at")),
        "finished_at": _iso(row.get("finished_at")),
    }


def _memory_pointers(outcomes: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [_outcome_ref(row) for row in outcomes]


def _outcomes_by_action(rows: list[Mapping[str, Any]]) -> dict[UUID, list[Mapping[str, Any]]]:
    grouped: dict[UUID, list[Mapping[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(row["action_id"], []).append(row)
    return grouped


def _expected_delta_from_outcomes(outcomes: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    fields = (
        "new_hosts_count",
        "new_services_count",
        "new_endpoints_count",
        "new_surface_nodes_count",
        "new_surface_edges_count",
        "new_surface_deltas_count",
    )
    return [
        {"metric": field, "recent_total": _sum_optional(outcomes, field)}
        for field in fields
        if _sum_optional(outcomes, field) > 0
    ]


def _outcome_ref(row: Mapping[str, Any]) -> dict[str, Any]:
    return {"type": "action_outcome", "id": str(row["outcome_id"]), "run_id": str(row["run_id"])}


def _artifact_ref(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "type": "raw_artifact",
        "id": str(row["artifact_id"]),
        "run_id": _str_or_none(row.get("run_id")),
        "artifact_type": row.get("artifact_type"),
        "sha256": row.get("sha256"),
        "size_bytes": row.get("size_bytes"),
        "retention_class": row.get("retention_class"),
        "sanitized_safe_for_llm": row.get("sanitized_safe_for_llm"),
    }


def _catalog_id(row: Mapping[str, Any]) -> str:
    capability = str(row.get("capability_id") or "unknown")
    profile = str(row.get("profile_id") or "default")
    return f"{capability}.{profile}"


def _action_disabled_reasons(status: str, target_status: str) -> list[str]:
    reasons: list[str] = []
    if status == "requires_approval":
        reasons.append("requires_approval")
    elif status in {"blocked", "rejected"}:
        reasons.append(status)
    elif status not in {"allowed", "queued"}:
        reasons.append(f"status:{status}")
    if target_status == "blocked":
        reasons.append("target_blocked")
    return reasons


def _dict(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _sum_optional(rows: list[Mapping[str, Any]], field: str) -> int:
    return sum(int(row.get(field) or 0) for row in rows)


def _dedupe_dicts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    selected: list[dict[str, Any]] = []
    for row in rows:
        key = (str(row.get("type", "")), str(row.get("id", row)))
        if key in seen:
            continue
        seen.add(key)
        selected.append(row)
    return selected


def _str_or_none(value: object) -> str | None:
    return None if value is None else str(value)


def _iso(value: object) -> str | None:
    if value is None:
        return None
    isoformat = getattr(value, "isoformat", None)
    return isoformat() if callable(isoformat) else str(value)
