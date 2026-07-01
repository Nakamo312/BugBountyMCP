"""Deterministic workbench memory graph mappers.

This module builds rebuildable read-side shapes from action outcomes and raw
artifact references. It does not summarize with an LLM, read raw artifact bodies,
or create actions/proposals.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from api.application.workbench import WorkbenchEdge, WorkbenchGraph, WorkbenchLens, WorkbenchNode, workbench_read_boundary


def build_memory_lens_graph(
    *,
    program_id: UUID,
    outcomes: list[Mapping[str, Any]],
    artifacts: list[Mapping[str, Any]],
    seed: str | None,
    depth: int,
    limit: int,
) -> WorkbenchGraph:
    """Build a temporal action-memory graph from persisted read rows."""
    nodes: list[WorkbenchNode] = []
    edges: list[WorkbenchEdge] = []
    node_ids: set[str] = set()
    edge_ids: set[str] = set()
    artifacts_by_run = _artifacts_by_run(artifacts)

    def add_node(node: WorkbenchNode) -> None:
        if node.id not in node_ids:
            node_ids.add(node.id)
            nodes.append(node)

    def add_edge(edge: WorkbenchEdge) -> None:
        if edge.id not in edge_ids:
            edge_ids.add(edge.id)
            edges.append(edge)

    root = _program_memory_node(program_id, outcomes, artifacts)
    add_node(root)
    for outcome in outcomes:
        day = _outcome_day(outcome)
        campaign = _campaign_key(outcome)
        day_node = _day_summary_node(program_id, day, _outcomes_for_day(outcomes, day))
        campaign_node = _campaign_summary_node(program_id, day, campaign, _outcomes_for_campaign(outcomes, day, campaign))
        action_node = _action_node(outcome)
        run_node = _run_node(outcome)
        observation_node = _observation_node(outcome)
        delta_node = _delta_node(outcome)

        for node in (day_node, campaign_node, action_node, run_node, observation_node):
            add_node(node)
        add_edge(_memory_edge(root.id, day_node.id, "HAS_DAY", "has day"))
        add_edge(_memory_edge(day_node.id, campaign_node.id, "HAS_CAMPAIGN", "has campaign"))
        add_edge(_memory_edge(campaign_node.id, action_node.id, "HAS_ACTION", "has action"))
        add_edge(_memory_edge(action_node.id, run_node.id, "HAS_RUN", "has run"))
        add_edge(_memory_edge(run_node.id, observation_node.id, "PRODUCED_OBSERVATION", "produced observation"))

        if delta_node is not None:
            add_node(delta_node)
            add_edge(_memory_edge(observation_node.id, delta_node.id, "HAS_DELTA", "has delta", delta_state="added"))

        for artifact in artifacts_by_run.get(str(outcome["run_id"]), [])[:5]:
            artifact_node = _artifact_node(artifact)
            add_node(artifact_node)
            add_edge(_memory_edge(observation_node.id, artifact_node.id, "HAS_ARTIFACT_REF", "has artifact ref"))

    if seed:
        nodes, edges = _filter_neighborhood(nodes, edges, seed=seed, depth=depth)
    if len(nodes) > limit:
        selected_ids = {node.id for node in nodes[:limit]}
        nodes = nodes[:limit]
        edges = [edge for edge in edges if edge.source in selected_ids and edge.target in selected_ids]

    return WorkbenchGraph(
        program_id=program_id,
        lens=WorkbenchLens.MEMORY,
        seed=seed,
        depth=depth,
        nodes=nodes,
        edges=edges,
        counts={
            "nodes": len(nodes),
            "edges": len(edges),
            "outcomes": len(outcomes),
            "artifacts": len(artifacts),
            "days": len({_outcome_day(outcome) for outcome in outcomes}),
            "campaigns": len({_campaign_key(outcome) for outcome in outcomes}),
        },
        boundary=workbench_read_boundary(surface="memory_lens_from_action_outcomes"),
    )


def build_entity_memory_tree(outcomes: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Build deterministic tree nodes for entity memory panels."""
    nodes: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(node: dict[str, Any]) -> None:
        node_id = str(node["id"])
        if node_id not in seen:
            seen.add(node_id)
            nodes.append(node)

    for outcome in outcomes:
        day = _outcome_day(outcome)
        campaign = _campaign_key(outcome)
        day_id = f"memory-day:{day}"
        campaign_id = f"memory-campaign:{day}:{campaign}"
        action_id = f"action:{outcome['action_id']}"
        run_id = f"run:{outcome['run_id']}"
        observation_id = f"observation:{outcome['outcome_id']}"
        add({"id": day_id, "kind": "day_summary", "parent_id": None, "label": day, "created_at": _iso(outcome.get("created_at"))})
        add({"id": campaign_id, "kind": "campaign_summary", "parent_id": day_id, "label": campaign, "created_at": _iso(outcome.get("created_at"))})
        add({"id": action_id, "kind": "action", "parent_id": campaign_id, "label": f"{outcome['capability_id']} / {outcome['profile_id']}", "created_at": _iso(outcome.get("created_at"))})
        add({"id": run_id, "kind": "run", "parent_id": action_id, "label": f"run {outcome['run_id']}", "evidence_ref": _outcome_ref(outcome), "created_at": _iso(outcome.get("created_at"))})
        add({"id": observation_id, "kind": "observation", "parent_id": run_id, "label": str(outcome.get("terminal_outcome") or outcome.get("status")), "evidence_ref": _outcome_ref(outcome), "created_at": _iso(outcome.get("created_at"))})
        if _delta_total(outcome) > 0:
            add({"id": f"delta:{outcome['outcome_id']}", "kind": "delta", "parent_id": observation_id, "label": f"{_delta_total(outcome)} new projection items", "evidence_ref": _outcome_ref(outcome), "created_at": _iso(outcome.get("created_at"))})
    return nodes


def build_entity_memory_summaries(
    outcomes: list[Mapping[str, Any]],
    artifacts: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Build deterministic summaries that point back to fragments."""
    if not outcomes and not artifacts:
        return [{"kind": "entity_action_memory_summary", "outcome_count": 0, "artifact_count": 0, "summary_is_truth": False}]
    by_day: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for outcome in outcomes:
        by_day[_outcome_day(outcome)].append(outcome)
    summaries: list[dict[str, Any]] = [
        {
            "kind": "entity_action_memory_summary",
            "outcome_count": len(outcomes),
            "artifact_count": len(artifacts),
            "information_gain_total": sum(float(row.get("information_gain_score") or 0.0) for row in outcomes),
            "new_surface_nodes_total": _sum(outcomes, "new_surface_nodes_count"),
            "new_surface_edges_total": _sum(outcomes, "new_surface_edges_count"),
            "new_surface_deltas_total": _sum(outcomes, "new_surface_deltas_count"),
            "summary_is_truth": False,
            "rebuild_from": ["action_outcomes", "raw_artifact references"],
        }
    ]
    for day, rows in sorted(by_day.items(), reverse=True):
        summaries.append(
            {
                "kind": "day_memory_summary",
                "day": day,
                "outcome_count": len(rows),
                "information_gain_total": sum(float(row.get("information_gain_score") or 0.0) for row in rows),
                "new_surface_nodes_total": _sum(rows, "new_surface_nodes_count"),
                "new_surface_edges_total": _sum(rows, "new_surface_edges_count"),
                "new_surface_deltas_total": _sum(rows, "new_surface_deltas_count"),
                "summary_is_truth": False,
            }
        )
    return summaries


def _program_memory_node(program_id: UUID, outcomes: list[Mapping[str, Any]], artifacts: list[Mapping[str, Any]]) -> WorkbenchNode:
    return WorkbenchNode(
        id=f"memory-program:{program_id}",
        entity_key=f"memory-program:{program_id}",
        node_type="memory_program_summary",
        label="Program memory",
        caption=f"{len(outcomes)} outcomes · {len(artifacts)} artifact refs",
        properties={"program_id": str(program_id), "summary_is_truth": False},
        metadata={"rebuild_from": ["action_outcomes", "raw_artifact references"]},
        badges=["memory", "program"],
        metrics={"outcome_count": len(outcomes), "artifact_count": len(artifacts)},
        staleness="unknown",
        confidence=1.0,
        source_refs=[{"type": "action_outcome_memory", "id": str(program_id)}],
    )


def _day_summary_node(program_id: UUID, day: str, outcomes: list[Mapping[str, Any]]) -> WorkbenchNode:
    return WorkbenchNode(
        id=f"memory-day:{program_id}:{day}",
        entity_key=f"memory-day:{program_id}:{day}",
        node_type="memory_day_summary",
        label=day,
        caption=f"{len(outcomes)} outcomes",
        properties={"day": day, "summary_is_truth": False},
        metadata={"rebuild_from": "action_outcomes"},
        badges=["day", "summary"],
        metrics={"outcome_count": len(outcomes), "information_gain_total": sum(float(row.get("information_gain_score") or 0.0) for row in outcomes)},
        confidence=1.0,
        source_refs=[{"type": "memory_day", "id": day}],
    )


def _campaign_summary_node(program_id: UUID, day: str, campaign: str, outcomes: list[Mapping[str, Any]]) -> WorkbenchNode:
    return WorkbenchNode(
        id=f"memory-campaign:{program_id}:{day}:{campaign}",
        entity_key=f"memory-campaign:{program_id}:{day}:{campaign}",
        node_type="memory_campaign_summary",
        label=campaign,
        caption=f"{len(outcomes)} outcomes",
        properties={"day": day, "campaign_id": None if campaign == "uncampaigned" else campaign, "summary_is_truth": False},
        badges=["campaign", "summary"],
        metrics={"outcome_count": len(outcomes), "delta_total": sum(_delta_total(row) for row in outcomes)},
        confidence=1.0,
        source_refs=[{"type": "memory_campaign", "id": campaign}],
    )


def _action_node(outcome: Mapping[str, Any]) -> WorkbenchNode:
    return WorkbenchNode(
        id=f"memory-action:{outcome['action_id']}",
        entity_key=f"memory-action:{outcome['action_id']}",
        node_type="action_run_group",
        label=f"{outcome['capability_id']} / {outcome['profile_id']}",
        caption=str(outcome.get("terminal_outcome") or outcome.get("status")),
        properties={"action_id": str(outcome["action_id"]), "capability_id": outcome.get("capability_id"), "profile_id": outcome.get("profile_id")},
        badges=["action", str(outcome.get("capability_id"))],
        metrics={"information_gain": float(outcome.get("information_gain_score") or 0.0)},
        evidence_refs=[_outcome_ref(outcome)],
        staleness="fresh",
        confidence=1.0,
        source_refs=[_outcome_ref(outcome)],
    )


def _run_node(outcome: Mapping[str, Any]) -> WorkbenchNode:
    return WorkbenchNode(
        id=f"memory-run:{outcome['run_id']}",
        entity_key=f"memory-run:{outcome['run_id']}",
        node_type="action_run",
        label=f"Run {str(outcome['run_id'])[:8]}",
        caption=str(outcome.get("event_name") or outcome.get("node_id") or "action run"),
        properties={"run_id": str(outcome["run_id"]), "job_id": str(outcome["job_id"]), "attempt": outcome.get("attempt")},
        badges=["run", str(outcome.get("status"))],
        metrics={"duration_ms": outcome.get("duration_ms"), "error_count": outcome.get("error_count")},
        evidence_refs=[_outcome_ref(outcome)],
        confidence=1.0,
        source_refs=[_outcome_ref(outcome)],
    )


def _observation_node(outcome: Mapping[str, Any]) -> WorkbenchNode:
    observations = {
        "hosts": outcome.get("observed_hosts_count"),
        "services": outcome.get("observed_services_count"),
        "endpoints": outcome.get("observed_endpoints_count"),
        "http": outcome.get("http_observation_count"),
        "javascript_refs": outcome.get("javascript_reference_count"),
        "raw_artifacts": outcome.get("raw_artifact_count"),
    }
    return WorkbenchNode(
        id=f"memory-observation:{outcome['outcome_id']}",
        entity_key=f"memory-observation:{outcome['outcome_id']}",
        node_type="observation",
        label=str(outcome.get("terminal_outcome") or outcome.get("status")),
        caption=f"{sum(int(value or 0) for value in observations.values())} observed items",
        properties={"outcome_id": str(outcome["outcome_id"]), "node_id": outcome.get("node_id"), "event_name": outcome.get("event_name")},
        metadata={"observations": observations, "feedback": _feedback(outcome)},
        badges=["observation", str(outcome.get("terminal_outcome") or outcome.get("status"))],
        metrics={"observations": observations, "information_gain": float(outcome.get("information_gain_score") or 0.0)},
        evidence_refs=[_outcome_ref(outcome)],
        confidence=1.0,
        source_refs=[_outcome_ref(outcome)],
    )


def _delta_node(outcome: Mapping[str, Any]) -> WorkbenchNode | None:
    delta = {
        "hosts": outcome.get("new_hosts_count"),
        "services": outcome.get("new_services_count"),
        "endpoints": outcome.get("new_endpoints_count"),
        "surface_nodes": outcome.get("new_surface_nodes_count"),
        "surface_edges": outcome.get("new_surface_edges_count"),
        "surface_clusters": outcome.get("new_surface_clusters_count"),
        "surface_deltas": outcome.get("new_surface_deltas_count"),
        "graph_facts": outcome.get("new_graph_facts_count"),
        "search_documents": outcome.get("new_search_documents_count"),
    }
    total = sum(int(value or 0) for value in delta.values())
    if total <= 0:
        return None
    return WorkbenchNode(
        id=f"memory-delta:{outcome['outcome_id']}",
        entity_key=f"memory-delta:{outcome['outcome_id']}",
        node_type="delta",
        label=f"{total} new items",
        caption="derived from action outcome counters",
        properties={"outcome_id": str(outcome["outcome_id"]), "summary_is_truth": False},
        metadata={"delta": delta},
        badges=["delta"],
        metrics=delta,
        evidence_refs=[_outcome_ref(outcome)],
        staleness="fresh",
        confidence=1.0,
        source_refs=[_outcome_ref(outcome)],
    )


def _artifact_node(artifact: Mapping[str, Any]) -> WorkbenchNode:
    return WorkbenchNode(
        id=f"memory-artifact:{artifact['artifact_id']}",
        entity_key=f"memory-artifact:{artifact['artifact_id']}",
        node_type="artifact_ref",
        label=str(artifact.get("artifact_type") or "artifact"),
        caption=str(artifact.get("sha256") or artifact.get("artifact_id"))[:16],
        properties={
            "artifact_id": str(artifact["artifact_id"]),
            "run_id": _str_or_none(artifact.get("run_id")),
            "artifact_type": artifact.get("artifact_type"),
            "sha256": artifact.get("sha256"),
            "size_bytes": artifact.get("size_bytes"),
            "retention_class": artifact.get("retention_class"),
            "sanitized_safe_for_llm": artifact.get("sanitized_safe_for_llm"),
        },
        badges=["artifact", str(artifact.get("artifact_type") or "unknown")],
        evidence_refs=[_artifact_ref(artifact)],
        confidence=1.0 if artifact.get("sanitized_safe_for_llm") else 0.5,
        source_refs=[_artifact_ref(artifact)],
    )


def _memory_edge(source: str, target: str, relationship_type: str, label: str, *, delta_state: str = "unchanged") -> WorkbenchEdge:
    return WorkbenchEdge(
        id=f"edge:{source}:{relationship_type}:{target}",
        source=source,
        target=target,
        relationship_type=relationship_type,
        label=label,
        confidence=1.0,
        delta_state=delta_state,
        source_projection="action_outcome_memory",
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
    filtered_nodes = [node for node in nodes if node.id in selected]
    filtered_edges = [edge for edge in edges if edge.source in selected and edge.target in selected]
    return filtered_nodes, filtered_edges


def _artifacts_by_run(artifacts: list[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for artifact in artifacts:
        run_id = artifact.get("run_id")
        if run_id is not None:
            grouped[str(run_id)].append(artifact)
    return grouped


def _outcomes_for_day(outcomes: list[Mapping[str, Any]], day: str) -> list[Mapping[str, Any]]:
    return [outcome for outcome in outcomes if _outcome_day(outcome) == day]


def _outcomes_for_campaign(outcomes: list[Mapping[str, Any]], day: str, campaign: str) -> list[Mapping[str, Any]]:
    return [outcome for outcome in outcomes if _outcome_day(outcome) == day and _campaign_key(outcome) == campaign]


def _outcome_day(outcome: Mapping[str, Any]) -> str:
    value = outcome.get("finished_at") or outcome.get("created_at")
    date_method = getattr(value, "date", None)
    if callable(date_method):
        return date_method().isoformat()
    text = str(value or "unknown")
    return text[:10] if len(text) >= 10 else "unknown"


def _campaign_key(outcome: Mapping[str, Any]) -> str:
    return str(outcome.get("campaign_id") or "uncampaigned")


def _delta_total(outcome: Mapping[str, Any]) -> int:
    return sum(
        int(outcome.get(field) or 0)
        for field in (
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
    )


def _feedback(outcome: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "manual_interest": outcome.get("manual_interest"),
        "manual_stop": outcome.get("manual_stop"),
        "continued_by_followup": outcome.get("continued_by_followup"),
        "report_created": outcome.get("report_created"),
        "triage_outcome": outcome.get("triage_outcome"),
    }


def _outcome_ref(outcome: Mapping[str, Any]) -> dict[str, Any]:
    return {"type": "action_outcome", "id": str(outcome["outcome_id"]), "run_id": str(outcome["run_id"])}


def _artifact_ref(artifact: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "type": "raw_artifact",
        "id": str(artifact["artifact_id"]),
        "run_id": _str_or_none(artifact.get("run_id")),
        "artifact_type": artifact.get("artifact_type"),
        "sha256": artifact.get("sha256"),
        "size_bytes": artifact.get("size_bytes"),
        "retention_class": artifact.get("retention_class"),
        "sanitized_safe_for_llm": artifact.get("sanitized_safe_for_llm"),
    }


def _sum(rows: list[Mapping[str, Any]], field: str) -> int:
    return sum(int(row.get(field) or 0) for row in rows)


def _str_or_none(value: object) -> str | None:
    return None if value is None else str(value)


def _iso(value: object) -> str | None:
    if value is None:
        return None
    isoformat = getattr(value, "isoformat", None)
    return isoformat() if callable(isoformat) else str(value)
