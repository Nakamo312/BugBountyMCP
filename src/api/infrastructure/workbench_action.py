"""Action lifecycle lens builders for the dashboard workbench.

The action lens is a read-only projection over persisted action lifecycle rows:
action request, targets, policy/approval decisions, jobs, runs, outcomes, and
human feedback. It never submits actions, starts jobs, reads raw artifact bodies,
or promotes outcomes into findings.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from api.application.research.sanitizer import sanitize_text
from api.application.workbench import (
    WorkbenchActionAffordance,
    WorkbenchActionAffordanceList,
    WorkbenchEdge,
    WorkbenchEntityMemory,
    WorkbenchEntityProfile,
    WorkbenchGraph,
    WorkbenchLens,
    WorkbenchNode,
    workbench_read_boundary,
)

_ACTION_ENTITY_PREFIXES = (
    "action-lifecycle:",
    "action:",
    "action-target:",
    "policy-decision:",
    "approval-request:",
    "approval-decision:",
    "action-job:",
    "action-run:",
    "action-outcome:",
    "action-delta:",
    "outcome-feedback:",
)


def build_action_lens_graph(
    *,
    program_id: UUID,
    actions: list[Mapping[str, Any]],
    targets: list[Mapping[str, Any]],
    policy_decisions: list[Mapping[str, Any]],
    approval_requests: list[Mapping[str, Any]],
    approval_decisions: list[Mapping[str, Any]],
    jobs: list[Mapping[str, Any]],
    runs: list[Mapping[str, Any]],
    outcomes: list[Mapping[str, Any]],
    feedback_events: list[Mapping[str, Any]],
    seed: str | None,
    depth: int,
    limit: int,
) -> WorkbenchGraph:
    """Build the action lifecycle graph without adding execution surfaces."""
    targets_by_action = _group(targets, "action_id")
    policies_by_action = _group(policy_decisions, "action_id")
    approval_requests_by_action = _group(approval_requests, "action_id")
    approval_decisions_by_request = _group(approval_decisions, "approval_request_id")
    jobs_by_action = _group(jobs, "action_id")
    runs_by_job = _group(runs, "job_id")
    outcomes_by_run = _group(outcomes, "run_id")
    outcomes_by_action = _group(outcomes, "action_id")
    feedback_by_outcome = _group(feedback_events, "outcome_id")

    nodes: list[WorkbenchNode] = []
    edges: list[WorkbenchEdge] = []
    node_ids: set[str] = set()
    edge_ids: set[str] = set()

    def add_node(node: WorkbenchNode) -> None:
        if node.id not in node_ids:
            node_ids.add(node.id)
            nodes.append(node)

    def add_edge(edge: WorkbenchEdge) -> None:
        if edge.id not in edge_ids:
            edge_ids.add(edge.id)
            edges.append(edge)

    root = _overview_node(program_id, actions, jobs, runs, outcomes, feedback_events)
    add_node(root)

    for action in actions:
        action_node = _action_node(action, targets_by_action.get(str(action["action_id"]), []), outcomes_by_action.get(str(action["action_id"]), []))
        add_node(action_node)
        add_edge(_action_edge(root.id, action_node.id, "HAS_ACTION", "has action", delta_state=_status_delta(action.get("status"))))

        for target in targets_by_action.get(str(action["action_id"]), []):
            target_node = _target_node(target)
            add_node(target_node)
            add_edge(_action_edge(action_node.id, target_node.id, "HAS_TARGET", "has target", delta_state=_target_delta(target.get("status"))))

        for policy in policies_by_action.get(str(action["action_id"]), []):
            policy_node = _policy_node(policy)
            add_node(policy_node)
            add_edge(_action_edge(action_node.id, policy_node.id, "HAS_POLICY_DECISION", "has policy decision", delta_state=_status_delta(policy.get("status"))))

        for approval in approval_requests_by_action.get(str(action["action_id"]), []):
            approval_node = _approval_request_node(approval)
            add_node(approval_node)
            add_edge(_action_edge(action_node.id, approval_node.id, "HAS_APPROVAL_REQUEST", "has approval request", delta_state=_approval_delta(approval.get("status"))))
            for decision in approval_decisions_by_request.get(str(approval["approval_request_id"]), []):
                decision_node = _approval_decision_node(decision)
                add_node(decision_node)
                add_edge(_action_edge(approval_node.id, decision_node.id, "HAS_APPROVAL_DECISION", "has approval decision", delta_state=_decision_delta(decision.get("decision"))))

        for job in jobs_by_action.get(str(action["action_id"]), []):
            job_node = _job_node(job)
            add_node(job_node)
            add_edge(_action_edge(action_node.id, job_node.id, "ENQUEUED_JOB", "enqueued job", delta_state=_status_delta(job.get("status"))))
            for run in runs_by_job.get(str(job["job_id"]), []):
                run_node = _run_node(run)
                add_node(run_node)
                add_edge(_action_edge(job_node.id, run_node.id, "HAS_RUN", "has run", delta_state=_status_delta(run.get("status"))))
                for outcome in outcomes_by_run.get(str(run["run_id"]), []):
                    outcome_node = _outcome_node(outcome)
                    add_node(outcome_node)
                    add_edge(_action_edge(run_node.id, outcome_node.id, "PRODUCED_OUTCOME", "produced outcome", delta_state=_outcome_delta(outcome)))
                    delta_node = _delta_node(outcome)
                    if delta_node is not None:
                        add_node(delta_node)
                        add_edge(_action_edge(outcome_node.id, delta_node.id, "HAS_DELTA", "has delta", delta_state="added"))
                    for feedback in feedback_by_outcome.get(str(outcome["outcome_id"]), []):
                        feedback_node = _feedback_node(feedback)
                        add_node(feedback_node)
                        add_edge(_action_edge(outcome_node.id, feedback_node.id, "HAS_FEEDBACK", "has feedback", delta_state="changed"))

    if seed:
        nodes, edges = _filter_neighborhood(nodes, edges, seed=seed, depth=depth)
    if len(nodes) > limit:
        selected_ids = {node.id for node in nodes[:limit]}
        nodes = nodes[:limit]
        edges = [edge for edge in edges if edge.source in selected_ids and edge.target in selected_ids]

    return WorkbenchGraph(
        program_id=program_id,
        lens=WorkbenchLens.ACTION,
        seed=seed,
        depth=depth,
        nodes=nodes,
        edges=edges,
        counts={
            "nodes": len(nodes),
            "edges": len(edges),
            "actions": len(actions),
            "targets": len(targets),
            "policy_decisions": len(policy_decisions),
            "approval_requests": len(approval_requests),
            "approval_decisions": len(approval_decisions),
            "jobs": len(jobs),
            "runs": len(runs),
            "outcomes": len(outcomes),
            "feedback_events": len(feedback_events),
        },
        boundary=workbench_read_boundary(surface="action_lens_lifecycle_read_model"),
    )


def action_entity_profile_from_graph(*, program_id: UUID, entity_key: str, graph: WorkbenchGraph) -> WorkbenchEntityProfile | None:
    node = _node_by_entity_key(graph, entity_key)
    if node is None:
        return None
    return WorkbenchEntityProfile(
        program_id=program_id,
        entity_key=entity_key,
        profile={
            "node_id": node.id,
            "node_type": node.node_type,
            "label": node.label,
            "caption": node.caption,
            "lens": WorkbenchLens.ACTION.value,
        },
        properties=node.properties,
        evidence_refs=node.evidence_refs,
        related_outcomes=_related_outcomes(node),
        related_actions=_related_actions(node),
        memory_pointers=node.source_refs,
        boundary=workbench_read_boundary(surface="action_entity_profile"),
    )


def action_entity_memory_from_graph(*, program_id: UUID, entity_key: str, graph: WorkbenchGraph) -> WorkbenchEntityMemory | None:
    node = _node_by_entity_key(graph, entity_key)
    if node is None:
        return None
    fragment = {
        "kind": "action_lens_node",
        "id": node.id,
        "entity_key": node.entity_key,
        "node_type": node.node_type,
        "label": node.label,
        "properties": node.properties,
        "metrics": node.metrics,
        "badges": node.badges,
        "summary_is_truth": False,
        "rebuild_from": [
            "action_requests",
            "action_request_targets",
            "policy_decisions",
            "approval_requests",
            "approval_decisions",
            "jobs",
            "runs",
            "action_outcomes",
            "action_outcome_feedback_events",
        ],
    }
    return WorkbenchEntityMemory(
        program_id=program_id,
        entity_key=entity_key,
        fragments=[fragment],
        tree_nodes=[
            {
                "id": node.id,
                "kind": node.node_type,
                "parent_id": None,
                "label": node.label,
                "evidence_ref": node.source_refs[0] if node.source_refs else None,
            }
        ],
        summaries=[
            {
                "kind": "action_lifecycle_summary",
                "node_type": node.node_type,
                "summary_is_truth": False,
                "execution_surface": False,
            }
        ],
        evidence_refs=node.evidence_refs,
        boundary=workbench_read_boundary(surface="action_entity_memory"),
    )


def action_entity_actions(*, program_id: UUID, entity_key: str) -> WorkbenchActionAffordanceList:
    return WorkbenchActionAffordanceList(
        program_id=program_id,
        entity_key=entity_key,
        actions=[],
        boundary=workbench_read_boundary(surface="action_lens_read_only_no_action_affordances"),
    )


def is_action_entity_key(entity_key: str) -> bool:
    return entity_key.startswith(_ACTION_ENTITY_PREFIXES)


def _overview_node(
    program_id: UUID,
    actions: list[Mapping[str, Any]],
    jobs: list[Mapping[str, Any]],
    runs: list[Mapping[str, Any]],
    outcomes: list[Mapping[str, Any]],
    feedback_events: list[Mapping[str, Any]],
) -> WorkbenchNode:
    statuses = _counts_by(actions, "status")
    return WorkbenchNode(
        id=f"action-lifecycle:{program_id}",
        entity_key=f"action-lifecycle:{program_id}",
        node_type="action_lifecycle_overview",
        label="Action lifecycle",
        caption=f"{len(actions)} actions · {len(runs)} runs · {len(outcomes)} outcomes",
        properties={"program_id": str(program_id), "execution_surface": False},
        metadata={"status_counts": statuses, "lifecycle_contract": _lifecycle_contract()},
        badges=["action", "read-only"],
        metrics={
            "actions": len(actions),
            "jobs": len(jobs),
            "runs": len(runs),
            "outcomes": len(outcomes),
            "feedback_events": len(feedback_events),
            **{f"status_{status}": count for status, count in statuses.items()},
        },
        confidence=1.0,
        source_refs=[{"type": "action_lifecycle", "id": str(program_id)}],
    )


def _action_node(action: Mapping[str, Any], targets: list[Mapping[str, Any]], outcomes: list[Mapping[str, Any]]) -> WorkbenchNode:
    action_id = str(action["action_id"])
    status = str(action.get("status") or "unknown")
    delta_total = sum(_delta_total(outcome) for outcome in outcomes)
    return WorkbenchNode(
        id=f"action:{action_id}",
        entity_key=f"action:{action_id}",
        node_type="allowed_action",
        label=f"{action.get('capability_id')} / {action.get('profile_id')}",
        caption=f"{status} · {len(targets)} targets · {len(outcomes)} outcomes",
        properties={
            "action_id": action_id,
            "catalog_entry_id": _str_or_none(action.get("catalog_entry_id")),
            "catalog_id": _catalog_id(action),
            "capability_id": action.get("capability_id"),
            "profile_id": action.get("profile_id"),
            "requested_by": action.get("requested_by"),
            "campaign_id": _str_or_none(action.get("campaign_id")),
            "correlation_id": _str_or_none(action.get("correlation_id")),
            "status": status,
            "target_count": len(targets),
            "outcome_count": len(outcomes),
            "created_at": _iso(action.get("created_at")),
            "updated_at": _iso(action.get("updated_at")),
            "execution_surface": False,
        },
        metadata={"request_summary": _request_summary(action), "lifecycle_contract": _lifecycle_contract()},
        badges=_badges("action", status),
        metrics={"targets": len(targets), "outcomes": len(outcomes), "delta_total": delta_total},
        evidence_refs=[{"type": "action_request", "id": action_id}],
        action_affordance_count=0,
        staleness=_status_staleness(status),
        confidence=_status_confidence(status),
        source_refs=[{"type": "action_request", "id": action_id}],
    )


def _target_node(target: Mapping[str, Any]) -> WorkbenchNode:
    target_id = str(target["target_id"])
    status = str(target.get("target_status") or "unknown")
    target_value = str(target.get("target") or "")
    return WorkbenchNode(
        id=f"action-target:{target_id}",
        entity_key=f"action-target:{target_id}",
        node_type="action_target",
        label=_short_label(target_value, 80),
        caption=status,
        properties={
            "target_id": target_id,
            "action_id": str(target["action_id"]),
            "position": target.get("position"),
            "status": status,
            "target": _short_label(target_value, 200),
            "created_at": _iso(target.get("created_at")),
        },
        badges=_badges("target", status),
        evidence_refs=[{"type": "action_request_target", "id": target_id}],
        staleness="stale" if status == "blocked" else "fresh",
        confidence=1.0,
        source_refs=[{"type": "action_request_target", "id": target_id}],
    )


def _policy_node(policy: Mapping[str, Any]) -> WorkbenchNode:
    policy_id = str(policy["policy_decision_id"])
    status = str(policy.get("status") or "unknown")
    reasons = _safe_list(policy.get("reasons"))[:5]
    return WorkbenchNode(
        id=f"policy-decision:{policy_id}",
        entity_key=f"policy-decision:{policy_id}",
        node_type="policy_decision",
        label=f"Policy {status}",
        caption=f"{policy.get('safety_level') or 'unknown safety'} · {len(reasons)} reasons",
        properties={
            "policy_decision_id": policy_id,
            "action_id": str(policy["action_id"]),
            "status": status,
            "safety_level": policy.get("safety_level"),
            "catalog_hash": policy.get("catalog_hash"),
            "created_at": _iso(policy.get("created_at")),
        },
        metadata={
            "reasons": [_sanitize_reason(reason) for reason in reasons],
            "allowed_target_count": len(_safe_list(policy.get("allowed_targets"))),
            "blocked_target_count": len(_safe_list(policy.get("blocked_targets"))),
        },
        badges=_badges("policy", status),
        evidence_refs=[{"type": "policy_decision", "id": policy_id}],
        staleness=_status_staleness(status),
        confidence=_status_confidence(status),
        source_refs=[{"type": "policy_decision", "id": policy_id}],
    )


def _approval_request_node(approval: Mapping[str, Any]) -> WorkbenchNode:
    approval_id = str(approval["approval_request_id"])
    status = str(approval.get("status") or "unknown")
    return WorkbenchNode(
        id=f"approval-request:{approval_id}",
        entity_key=f"approval-request:{approval_id}",
        node_type="approval_request",
        label=f"Approval {status}",
        caption=_sanitize_reason(approval.get("reason")) or str(approval.get("requested_by") or "policy"),
        properties={
            "approval_request_id": approval_id,
            "action_id": str(approval["action_id"]),
            "policy_decision_id": _str_or_none(approval.get("policy_decision_id")),
            "status": status,
            "requested_by": approval.get("requested_by"),
            "created_at": _iso(approval.get("created_at")),
            "decided_at": _iso(approval.get("decided_at")),
        },
        metadata={"reason_excerpt": _sanitize_reason(approval.get("reason"))},
        badges=_badges("approval", status),
        evidence_refs=[{"type": "approval_request", "id": approval_id}],
        staleness="stale" if status in {"rejected", "cancelled"} else "fresh",
        confidence=0.8 if status == "pending" else 1.0,
        source_refs=[{"type": "approval_request", "id": approval_id}],
    )


def _approval_decision_node(decision: Mapping[str, Any]) -> WorkbenchNode:
    decision_id = str(decision["approval_decision_id"])
    decision_value = str(decision.get("decision") or "unknown")
    return WorkbenchNode(
        id=f"approval-decision:{decision_id}",
        entity_key=f"approval-decision:{decision_id}",
        node_type="approval_decision",
        label=f"Approval {decision_value}",
        caption=str(decision.get("decided_by") or "unknown actor"),
        properties={
            "approval_decision_id": decision_id,
            "approval_request_id": str(decision["approval_request_id"]),
            "action_id": str(decision["action_id"]),
            "decision": decision_value,
            "decided_by": decision.get("decided_by"),
            "created_at": _iso(decision.get("created_at")),
        },
        metadata={"reason_excerpt": _sanitize_reason(decision.get("reason"))},
        badges=_badges("decision", decision_value),
        evidence_refs=[{"type": "approval_decision", "id": decision_id}],
        staleness="fresh" if decision_value == "approved" else "stale",
        confidence=1.0,
        source_refs=[{"type": "approval_decision", "id": decision_id}],
    )


def _job_node(job: Mapping[str, Any]) -> WorkbenchNode:
    job_id = str(job["job_id"])
    status = str(job.get("status") or "unknown")
    return WorkbenchNode(
        id=f"action-job:{job_id}",
        entity_key=f"action-job:{job_id}",
        node_type="action_job",
        label=f"Job {status}",
        caption=f"{job.get('capability_id')} / {job.get('profile_id')}",
        properties={
            "job_id": job_id,
            "action_id": str(job["action_id"]),
            "campaign_id": _str_or_none(job.get("campaign_id")),
            "correlation_id": _str_or_none(job.get("correlation_id")),
            "status": status,
            "created_at": _iso(job.get("created_at")),
            "updated_at": _iso(job.get("updated_at")),
        },
        badges=_badges("job", status),
        evidence_refs=[{"type": "job", "id": job_id}],
        staleness=_status_staleness(status),
        confidence=_runtime_confidence(status),
        source_refs=[{"type": "job", "id": job_id}],
    )


def _run_node(run: Mapping[str, Any]) -> WorkbenchNode:
    run_id = str(run["run_id"])
    status = str(run.get("status") or "unknown")
    return WorkbenchNode(
        id=f"action-run:{run_id}",
        entity_key=f"action-run:{run_id}",
        node_type="action_run",
        label=f"Run {status}",
        caption=f"attempt {run.get('attempt')} · {run.get('execution_mode')}",
        properties={
            "run_id": run_id,
            "job_id": str(run["job_id"]),
            "node_id": run.get("node_id"),
            "event_name": run.get("event_name"),
            "execution_mode": run.get("execution_mode"),
            "status": status,
            "terminal_outcome": run.get("terminal_outcome"),
            "attempt": run.get("attempt"),
            "target_count": run.get("target_count"),
            "needs_reconcile": bool(run.get("needs_reconcile")),
            "retry_reason": run.get("retry_reason"),
            "created_at": _iso(run.get("created_at")),
            "started_at": _iso(run.get("started_at")),
            "finished_at": _iso(run.get("finished_at")),
        },
        metadata={"error_excerpt": _sanitize_reason(run.get("error"))},
        badges=_badges("run", status),
        evidence_refs=[{"type": "run", "id": run_id}],
        staleness=_status_staleness(status),
        confidence=_runtime_confidence(status),
        source_refs=[{"type": "run", "id": run_id}],
    )


def _outcome_node(outcome: Mapping[str, Any]) -> WorkbenchNode:
    outcome_id = str(outcome["outcome_id"])
    status = str(outcome.get("terminal_outcome") or outcome.get("status") or "unknown")
    return WorkbenchNode(
        id=f"action-outcome:{outcome_id}",
        entity_key=f"action-outcome:{outcome_id}",
        node_type="action_outcome",
        label=f"Outcome {status}",
        caption=f"gain {float(outcome.get('information_gain_score') or 0.0):.2f} · {_delta_total(outcome)} deltas",
        properties={
            "outcome_id": outcome_id,
            "action_id": str(outcome["action_id"]),
            "job_id": str(outcome["job_id"]),
            "run_id": str(outcome["run_id"]),
            "capability_id": outcome.get("capability_id"),
            "profile_id": outcome.get("profile_id"),
            "node_id": outcome.get("node_id"),
            "event_name": outcome.get("event_name"),
            "status": outcome.get("status"),
            "terminal_outcome": outcome.get("terminal_outcome"),
            "attempt": outcome.get("attempt"),
            "duration_ms": outcome.get("duration_ms"),
            "error_count": outcome.get("error_count"),
            "created_at": _iso(outcome.get("created_at")),
            "finished_at": _iso(outcome.get("finished_at")),
        },
        metadata={"score_breakdown": _dict(outcome.get("score_breakdown")), "feedback": _outcome_feedback_inline(outcome)},
        badges=_badges("outcome", status),
        metrics={
            "information_gain": float(outcome.get("information_gain_score") or 0.0),
            "delta_total": _delta_total(outcome),
            "raw_artifacts": int(outcome.get("raw_artifact_count") or 0),
            "observed_endpoints": int(outcome.get("observed_endpoints_count") or 0),
        },
        evidence_refs=[{"type": "action_outcome", "id": outcome_id, "run_id": str(outcome["run_id"])}],
        staleness="fresh" if status in {"completed", "partial"} else "stale",
        confidence=1.0 if outcome.get("terminal_outcome") else 0.7,
        source_refs=[{"type": "action_outcome", "id": outcome_id, "run_id": str(outcome["run_id"])}],
    )


def _delta_node(outcome: Mapping[str, Any]) -> WorkbenchNode | None:
    total = _delta_total(outcome)
    if total <= 0:
        return None
    outcome_id = str(outcome["outcome_id"])
    return WorkbenchNode(
        id=f"action-delta:{outcome_id}",
        entity_key=f"action-delta:{outcome_id}",
        node_type="action_delta",
        label=f"{total} new projection items",
        caption="derived from action_outcomes counters",
        properties={
            "outcome_id": outcome_id,
            "action_id": str(outcome["action_id"]),
            "run_id": str(outcome["run_id"]),
            "new_hosts_count": outcome.get("new_hosts_count"),
            "new_services_count": outcome.get("new_services_count"),
            "new_endpoints_count": outcome.get("new_endpoints_count"),
            "new_surface_nodes_count": outcome.get("new_surface_nodes_count"),
            "new_surface_edges_count": outcome.get("new_surface_edges_count"),
            "new_surface_deltas_count": outcome.get("new_surface_deltas_count"),
            "new_graph_facts_count": outcome.get("new_graph_facts_count"),
            "new_search_documents_count": outcome.get("new_search_documents_count"),
            "summary_is_truth": False,
        },
        metadata={"rebuild_from": "action_outcomes"},
        badges=["delta", "derived"],
        metrics={"delta_total": total},
        evidence_refs=[{"type": "action_outcome", "id": outcome_id}],
        staleness="fresh",
        confidence=1.0,
        source_refs=[{"type": "action_outcome_delta", "id": outcome_id}],
    )


def _feedback_node(feedback: Mapping[str, Any]) -> WorkbenchNode:
    feedback_id = str(feedback["feedback_id"])
    signals = _feedback_signals(feedback)
    return WorkbenchNode(
        id=f"outcome-feedback:{feedback_id}",
        entity_key=f"outcome-feedback:{feedback_id}",
        node_type="outcome_feedback",
        label="Outcome feedback",
        caption=f"{feedback.get('actor')} · {feedback.get('source')}",
        properties={
            "feedback_id": feedback_id,
            "outcome_id": str(feedback["outcome_id"]),
            "action_id": str(feedback["action_id"]),
            "job_id": str(feedback["job_id"]),
            "run_id": str(feedback["run_id"]),
            "actor": feedback.get("actor"),
            "source": feedback.get("source"),
            "confidence": float(feedback.get("confidence") or 0.0),
            "created_at": _iso(feedback.get("created_at")),
        },
        metadata={"signals": signals, "reason_excerpt": _sanitize_reason(feedback.get("reason"))},
        badges=["feedback", *signals],
        metrics={"confidence": float(feedback.get("confidence") or 0.0)},
        evidence_refs=[{"type": "action_outcome_feedback", "id": feedback_id}],
        staleness="fresh",
        confidence=float(feedback.get("confidence") or 0.5),
        source_refs=[{"type": "action_outcome_feedback", "id": feedback_id}],
    )


def _action_edge(source: str, target: str, relationship_type: str, label: str, *, delta_state: str = "unchanged") -> WorkbenchEdge:
    return WorkbenchEdge(
        id=f"edge:{source}:{relationship_type}:{target}",
        source=source,
        target=target,
        relationship_type=relationship_type,
        label=label,
        confidence=1.0,
        delta_state=delta_state,
        source_projection="action_lifecycle",
    )


def _filter_neighborhood(nodes: list[WorkbenchNode], edges: list[WorkbenchEdge], *, seed: str, depth: int) -> tuple[list[WorkbenchNode], list[WorkbenchEdge]]:
    seed_ids = {node.id for node in nodes if seed in {node.id, node.entity_key}}
    if not seed_ids:
        return [], []
    selected = set(seed_ids)
    frontier = set(seed_ids)
    for _ in range(max(0, depth)):
        next_frontier: set[str] = set()
        for edge in edges:
            if edge.source in frontier and edge.target not in selected:
                next_frontier.add(edge.target)
            if edge.target in frontier and edge.source not in selected:
                next_frontier.add(edge.source)
        if not next_frontier:
            break
        selected.update(next_frontier)
        frontier = next_frontier
    selected_nodes = [node for node in nodes if node.id in selected]
    selected_edges = [edge for edge in edges if edge.source in selected and edge.target in selected]
    return selected_nodes, selected_edges


def _node_by_entity_key(graph: WorkbenchGraph, entity_key: str) -> WorkbenchNode | None:
    return next((node for node in graph.nodes if node.entity_key == entity_key or node.id == entity_key), None)


def _related_actions(node: WorkbenchNode) -> list[dict[str, Any]]:
    action_id = node.properties.get("action_id")
    if action_id is None and node.node_type == "allowed_action":
        action_id = node.properties.get("action_id")
    if action_id is None:
        return []
    return [{"action_id": str(action_id), "catalog_id": node.properties.get("catalog_id"), "status": node.properties.get("status")}]


def _related_outcomes(node: WorkbenchNode) -> list[dict[str, Any]]:
    outcome_id = node.properties.get("outcome_id")
    if outcome_id is None:
        return []
    return [{"outcome_id": str(outcome_id), "run_id": node.properties.get("run_id"), "status": node.properties.get("terminal_outcome") or node.properties.get("status")}]


def _group(rows: list[Mapping[str, Any]], key: str) -> dict[str, list[Mapping[str, Any]]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        value = row.get(key)
        if value is not None:
            grouped[str(value)].append(row)
    return grouped


def _counts_by(rows: list[Mapping[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(field) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return counts


def _badges(kind: str, status: str) -> list[str]:
    badges = [kind]
    if status:
        badges.append(status)
    if status in {"blocked", "rejected", "failed", "dead", "cancelled", "policy_blocked", "tool_failed"}:
        badges.append("blocked")
    if status in {"queued", "leased", "running", "flushing", "requires_approval", "pending"}:
        badges.append("active")
    return badges


def _status_delta(status: object) -> str:
    value = str(status or "")
    if value in {"allowed", "queued", "running", "completed", "approved"}:
        return "unchanged"
    if value in {"blocked", "rejected", "failed", "dead", "cancelled"}:
        return "removed"
    if value in {"requires_approval", "pending", "leased", "flushing"}:
        return "changed"
    return "unknown"


def _target_delta(status: object) -> str:
    return "removed" if str(status or "") == "blocked" else "unchanged"


def _approval_delta(status: object) -> str:
    return "changed" if str(status or "") == "pending" else _status_delta(status)


def _decision_delta(decision: object) -> str:
    return "unchanged" if str(decision or "") == "approved" else "removed"


def _outcome_delta(outcome: Mapping[str, Any]) -> str:
    terminal = str(outcome.get("terminal_outcome") or "")
    if terminal in {"completed", "partial"}:
        return "changed" if _delta_total(outcome) > 0 else "unchanged"
    if terminal in {"tool_failed", "policy_blocked", "skipped"}:
        return "removed"
    return _status_delta(outcome.get("status"))


def _status_staleness(status: str) -> str:
    if status in {"allowed", "queued", "running", "leased", "flushing", "requires_approval", "pending"}:
        return "fresh"
    if status in {"blocked", "rejected", "failed", "dead", "cancelled", "tool_failed", "policy_blocked", "skipped"}:
        return "stale"
    return "unknown"


def _status_confidence(status: str) -> float:
    if status in {"allowed", "blocked", "rejected", "completed", "failed", "approved"}:
        return 1.0
    if status in {"queued", "running", "requires_approval", "pending"}:
        return 0.75
    return 0.5


def _runtime_confidence(status: str) -> float:
    if status in {"completed", "failed", "dead", "cancelled"}:
        return 1.0
    if status in {"queued", "leased", "running", "flushing"}:
        return 0.75
    return 0.5


def _delta_total(row: Mapping[str, Any]) -> int:
    fields = (
        "new_hosts_count",
        "new_services_count",
        "new_endpoints_count",
        "new_surface_nodes_count",
        "new_surface_edges_count",
        "new_surface_clusters_count",
        "new_surface_deltas_count",
        "new_graph_facts_count",
        "new_search_documents_count",
    )
    return sum(int(row.get(field) or 0) for field in fields)


def _feedback_signals(feedback: Mapping[str, Any]) -> list[str]:
    signals: list[str] = []
    for field in ("manual_interest", "manual_stop", "continued_by_followup", "report_created"):
        if feedback.get(field) is True:
            signals.append(field)
    if feedback.get("triage_outcome"):
        signals.append(str(feedback["triage_outcome"]))
    return signals or ["recorded"]


def _outcome_feedback_inline(outcome: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "manual_interest": outcome.get("manual_interest"),
        "manual_stop": outcome.get("manual_stop"),
        "continued_by_followup": outcome.get("continued_by_followup"),
        "report_created": outcome.get("report_created"),
        "triage_outcome": outcome.get("triage_outcome"),
    }


def _request_summary(action: Mapping[str, Any]) -> dict[str, Any]:
    request = _dict(action.get("request"))
    options = _dict(request.get("options"))
    return {
        "kind": request.get("kind"),
        "target_count": len(_safe_list(request.get("targets"))),
        "option_keys": sorted(str(key) for key in options.keys()),
        "budget": _dict(request.get("budget")),
    }


def _lifecycle_contract() -> dict[str, Any]:
    return {
        "kind": "read_only_action_lifecycle",
        "execution_surface": False,
        "not_semantics": "action_recommendation/direct_execution/finding/verdict",
        "rebuild_from": [
            "action_requests",
            "action_request_targets",
            "policy_decisions",
            "approval_requests",
            "approval_decisions",
            "jobs",
            "runs",
            "action_outcomes",
            "action_outcome_feedback_events",
        ],
    }


def _catalog_id(row: Mapping[str, Any]) -> str:
    return f"{row.get('capability_id') or 'unknown'}.{row.get('profile_id') or 'default'}"


def _safe_list(value: object) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _dict(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _sanitize_reason(value: object) -> str | None:
    if value is None:
        return None
    return sanitize_text(str(value), limit=300).safe_excerpt


def _short_label(value: str, limit: int) -> str:
    safe = sanitize_text(value, limit=limit).safe_excerpt
    return safe if len(safe) <= limit else f"{safe[: max(0, limit - 1)]}…"


def _str_or_none(value: object) -> str | None:
    return None if value is None else str(value)


def _iso(value: object) -> str | None:
    if value is None:
        return None
    isoformat = getattr(value, "isoformat", None)
    return isoformat() if callable(isoformat) else str(value)
