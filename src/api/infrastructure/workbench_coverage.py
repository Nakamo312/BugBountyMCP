"""Coverage lens read-model builders for the dashboard workbench.

Coverage here means structural workbench coverage: which entities have linked
runs/outcomes, which component signals indicate gaps, and which next contexts
are suggested by materialized component analysis. It is not a vulnerability,
risk, severity, or OWASP verdict model.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any
from uuid import UUID

from api.application.workbench import WorkbenchEdge, WorkbenchGraph, WorkbenchLens, WorkbenchNode, workbench_read_boundary


_UNCHECKED_GAP_LIMIT = 32
_COMPONENT_GAP_LIMIT = 24
_CHECKED_ENTITY_LIMIT = 24


def build_coverage_lens_graph(
    *,
    program_id: UUID,
    snapshot: Mapping[str, Any],
    node_rows: list[Mapping[str, Any]],
    delta_by_subject: Mapping[str, str],
    component_run: Mapping[str, Any] | None,
    component_items: list[Mapping[str, Any]],
    action_rows: list[Mapping[str, Any]],
    outcome_rows: list[Mapping[str, Any]],
    seed: str | None,
    depth: int,
    limit: int,
) -> WorkbenchGraph:
    checked_values = _checked_entity_values(action_rows, outcome_rows)
    coverage_rows = [_coverage_row(row, checked_values, delta_by_subject) for row in node_rows]
    component_gap_rows = _component_gap_rows(component_items)

    nodes: list[WorkbenchNode] = []
    edges: list[WorkbenchEdge] = []
    seen_edges: set[str] = set()

    def add_edge(edge: WorkbenchEdge) -> None:
        if edge.id not in seen_edges:
            seen_edges.add(edge.id)
            edges.append(edge)

    root = _overview_node(
        program_id=program_id,
        snapshot=snapshot,
        coverage_rows=coverage_rows,
        component_gap_rows=component_gap_rows,
        action_rows=action_rows,
        outcome_rows=outcome_rows,
    )
    nodes.append(root)

    lane_nodes = _structural_lane_nodes(program_id, coverage_rows)
    lane_by_type = {node.properties["node_type"]: node for node in lane_nodes}
    for lane in lane_nodes:
        nodes.append(lane)
        add_edge(_coverage_edge(root.id, lane.id, "HAS_COVERAGE_LANE", "has coverage lane"))

    capability_lanes = _capability_lane_nodes(program_id, action_rows, outcome_rows, component_items)
    for lane in capability_lanes:
        nodes.append(lane)
        add_edge(_coverage_edge(root.id, lane.id, "HAS_CAPABILITY_LANE", "has capability lane"))

    for checked in _checked_entity_nodes(program_id, coverage_rows)[:_CHECKED_ENTITY_LIMIT]:
        nodes.append(checked)
        lane = lane_by_type.get(checked.properties.get("node_type"))
        if lane is not None:
            add_edge(_coverage_edge(lane.id, checked.id, "HAS_CHECKED_ENTITY", "has checked entity"))

    for gap in _gap_nodes(program_id, coverage_rows)[:_UNCHECKED_GAP_LIMIT]:
        nodes.append(gap)
        lane = lane_by_type.get(gap.properties.get("node_type"))
        if lane is not None:
            add_edge(_coverage_edge(lane.id, gap.id, "HAS_GAP", "has gap", delta_state=gap.properties.get("delta_state", "unknown")))

    for gap in _component_gap_nodes(component_run, component_gap_rows)[:_COMPONENT_GAP_LIMIT]:
        nodes.append(gap)
        add_edge(_coverage_edge(root.id, gap.id, "HAS_COMPONENT_GAP", "has component gap"))
        for suggestion in _suggested_context_nodes(gap, component_gap_rows):
            nodes.append(suggestion)
            add_edge(_coverage_edge(gap.id, suggestion.id, "SUGGESTS_NEXT_CONTEXT", "suggests next context"))

    if seed:
        nodes, edges = _filter_neighborhood(nodes, edges, seed=seed, depth=depth)
    if len(nodes) > limit:
        selected_ids = {node.id for node in nodes[:limit]}
        nodes = nodes[:limit]
        edges = [edge for edge in edges if edge.source in selected_ids and edge.target in selected_ids]

    return WorkbenchGraph(
        program_id=program_id,
        lens=WorkbenchLens.COVERAGE,
        snapshot_id=snapshot["id"],
        seed=seed,
        depth=depth,
        nodes=nodes,
        edges=edges,
        counts={
            "nodes": len(nodes),
            "edges": len(edges),
            "surface_entities": len(coverage_rows),
            "checked_entities": sum(1 for row in coverage_rows if row["checked"]),
            "unchecked_entities": sum(1 for row in coverage_rows if not row["checked"]),
            "stale_entities": sum(1 for row in coverage_rows if row["stale"]),
            "component_gaps": len(component_gap_rows),
            "capability_lanes": len(capability_lanes),
        },
        boundary=workbench_read_boundary(surface="coverage_lens_structural_read_model"),
    )


def coverage_entity_profile_from_graph(
    *,
    program_id: UUID,
    entity_key: str,
    graph: WorkbenchGraph,
):
    from api.application.workbench import WorkbenchEntityProfile

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
            "lens": WorkbenchLens.COVERAGE.value,
        },
        properties=node.properties,
        evidence_refs=node.evidence_refs,
        related_actions=_related_actions_from_coverage_node(node),
        memory_pointers=node.source_refs,
        boundary=workbench_read_boundary(surface="coverage_entity_profile"),
    )


def coverage_entity_memory_from_graph(
    *,
    program_id: UUID,
    entity_key: str,
    graph: WorkbenchGraph,
):
    from api.application.workbench import WorkbenchEntityMemory

    node = _node_by_entity_key(graph, entity_key)
    if node is None:
        return None
    fragment = {
        "kind": "coverage_lens_node",
        "id": node.id,
        "entity_key": node.entity_key,
        "node_type": node.node_type,
        "label": node.label,
        "properties": node.properties,
        "metrics": node.metrics,
        "badges": node.badges,
        "summary_is_truth": False,
        "rebuild_from": ["surface_nodes", "surface_component_analysis_items", "action_requests", "action_outcomes"],
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
                "kind": "coverage_structural_summary",
                "node_type": node.node_type,
                "summary_is_truth": False,
                "not_semantics": "vulnerability/risk/severity/finding/verdict",
            }
        ],
        evidence_refs=node.evidence_refs,
        boundary=workbench_read_boundary(surface="coverage_entity_memory"),
    )


def is_coverage_entity_key(entity_key: str) -> bool:
    return entity_key.startswith("coverage-") or entity_key.startswith("suggested-next-context:")


def _overview_node(
    *,
    program_id: UUID,
    snapshot: Mapping[str, Any],
    coverage_rows: list[dict[str, Any]],
    component_gap_rows: list[Mapping[str, Any]],
    action_rows: list[Mapping[str, Any]],
    outcome_rows: list[Mapping[str, Any]],
) -> WorkbenchNode:
    checked = sum(1 for row in coverage_rows if row["checked"])
    unchecked = len(coverage_rows) - checked
    stale = sum(1 for row in coverage_rows if row["stale"])
    ratio = _ratio(checked, len(coverage_rows))
    return WorkbenchNode(
        id=f"coverage-overview:{program_id}",
        entity_key=f"coverage-overview:{program_id}",
        node_type="coverage_overview",
        label="Coverage overview",
        caption=f"{checked}/{len(coverage_rows)} checked · {unchecked} gaps · {stale} stale",
        properties={
            "program_id": str(program_id),
            "snapshot_id": str(snapshot["id"]),
            "snapshot_created_at": _iso(snapshot.get("created_at")),
            "coverage_is_verdict": False,
        },
        metadata={"coverage_contract": _coverage_signal_contract()},
        badges=["coverage", "structural"],
        metrics={
            "surface_entities": len(coverage_rows),
            "checked_entities": checked,
            "unchecked_entities": unchecked,
            "stale_entities": stale,
            "component_gaps": len(component_gap_rows),
            "actions": len(action_rows),
            "outcomes": len(outcome_rows),
            "checked_ratio": ratio,
        },
        confidence=ratio,
        source_refs=[{"type": "surface_snapshot", "id": str(snapshot["id"])}],
    )


def _structural_lane_nodes(program_id: UUID, coverage_rows: list[dict[str, Any]]) -> list[WorkbenchNode]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in coverage_rows:
        grouped[row["node_type"]].append(row)
    nodes = []
    for node_type, rows in sorted(grouped.items()):
        checked = sum(1 for row in rows if row["checked"])
        gaps = len(rows) - checked
        stale = sum(1 for row in rows if row["stale"])
        ratio = _ratio(checked, len(rows))
        nodes.append(
            WorkbenchNode(
                id=f"coverage-lane:surface-node-type:{node_type}",
                entity_key=f"coverage-lane:surface-node-type:{node_type}",
                node_type="coverage_lane",
                label=f"{node_type} coverage",
                caption=f"{checked}/{len(rows)} checked · {gaps} gaps · {stale} stale",
                properties={"lane_type": "surface_node_type", "node_type": node_type, "coverage_is_verdict": False},
                metadata={"coverage_contract": _coverage_signal_contract()},
                badges=["coverage_lane", node_type],
                metrics={"total": len(rows), "checked": checked, "unchecked": gaps, "stale": stale, "checked_ratio": ratio},
                staleness="stale" if stale else "fresh",
                confidence=ratio,
                source_refs=[{"type": "coverage_lane", "id": node_type}],
            )
        )
    return nodes


def _capability_lane_nodes(
    program_id: UUID,
    action_rows: list[Mapping[str, Any]],
    outcome_rows: list[Mapping[str, Any]],
    component_items: list[Mapping[str, Any]],
) -> list[WorkbenchNode]:
    del program_id
    grouped: dict[tuple[str, str], dict[str, Any]] = defaultdict(lambda: {"actions": 0, "outcomes": 0, "targets": set(), "candidate_count": 0, "information_gain": 0.0})
    for row in action_rows:
        key = _capability_key(row)
        grouped[key]["actions"] += 1
        if row.get("target"):
            grouped[key]["targets"].add(str(row["target"]))
    for row in outcome_rows:
        key = _capability_key(row)
        grouped[key]["outcomes"] += 1
        grouped[key]["information_gain"] += float(row.get("information_gain_score") or 0.0)
        if row.get("node_id"):
            grouped[key]["targets"].add(str(row["node_id"]))
    for item in component_items:
        for candidate in _candidates(item):
            key = _capability_key(candidate)
            grouped[key]["candidate_count"] += 1
    nodes = []
    for (capability, profile), metrics in sorted(grouped.items()):
        lane_id = _capability_lane_id(capability, profile)
        nodes.append(
            WorkbenchNode(
                id=lane_id,
                entity_key=lane_id,
                node_type="capability_lane",
                label=f"{capability} / {profile}",
                caption=f"{metrics['actions']} actions · {metrics['outcomes']} outcomes · {metrics['candidate_count']} candidates",
                properties={
                    "lane_type": "capability",
                    "capability_id": capability,
                    "profile_id": profile,
                    "coverage_is_verdict": False,
                },
                metadata={"coverage_contract": _coverage_signal_contract()},
                badges=["capability_lane", capability, profile],
                metrics={
                    "actions": metrics["actions"],
                    "outcomes": metrics["outcomes"],
                    "covered_targets": len(metrics["targets"]),
                    "candidate_count": metrics["candidate_count"],
                    "information_gain_total": metrics["information_gain"],
                },
                staleness="fresh" if metrics["outcomes"] else "unknown",
                confidence=1.0 if metrics["outcomes"] else 0.5,
                source_refs=[{"type": "capability_lane", "id": f"{capability}:{profile}"}],
            )
        )
    return nodes


def _checked_entity_nodes(program_id: UUID, coverage_rows: list[dict[str, Any]]) -> list[WorkbenchNode]:
    del program_id
    nodes = []
    for row in _sort_coverage_rows([row for row in coverage_rows if row["checked"]]):
        nodes.append(
            WorkbenchNode(
                id=f"coverage-checked:{row['node_fingerprint']}",
                entity_key=f"coverage-checked:{row['node_fingerprint']}",
                node_type="checked_entity",
                label=_surface_label(row),
                caption=f"{row['node_type']} · linked action/outcome",
                properties={**_surface_properties(row), "checked": True, "coverage_is_verdict": False},
                metadata={"surface_entity_key": row["surface_entity_key"], "coverage_contract": _coverage_signal_contract()},
                badges=["checked", row["node_type"]],
                metrics={"checked": 1},
                evidence_refs=row["evidence_refs"],
                staleness="stale" if row["stale"] else "fresh",
                confidence=1.0,
                source_refs=row["evidence_refs"],
            )
        )
    return nodes


def _gap_nodes(program_id: UUID, coverage_rows: list[dict[str, Any]]) -> list[WorkbenchNode]:
    del program_id
    rows = [row for row in coverage_rows if not row["checked"]]
    nodes = []
    for row in _sort_coverage_rows(rows):
        reason = "changed_without_linked_action_or_outcome" if row["delta_state"] in {"added", "changed"} else "no_linked_action_or_outcome"
        badges = ["gap", row["node_type"]]
        if row["delta_state"] in {"added", "changed"}:
            badges.append(row["delta_state"])
        if row["stale"]:
            badges.append("stale")
        nodes.append(
            WorkbenchNode(
                id=f"coverage-gap:{row['node_fingerprint']}",
                entity_key=f"coverage-gap:{row['node_fingerprint']}",
                node_type="coverage_gap",
                label=_surface_label(row),
                caption=f"{row['node_type']} · {reason}",
                properties={**_surface_properties(row), "reason": reason, "checked": False, "coverage_is_verdict": False},
                metadata={"surface_entity_key": row["surface_entity_key"], "coverage_contract": _coverage_signal_contract()},
                badges=badges,
                metrics={"checked": 0, "delta_weight": 1 if row["delta_state"] in {"added", "changed"} else 0},
                evidence_refs=row["evidence_refs"],
                staleness="stale" if row["stale"] else "unknown",
                confidence=0.0,
                source_refs=row["evidence_refs"],
            )
        )
    return nodes


def _component_gap_nodes(component_run: Mapping[str, Any] | None, component_rows: list[Mapping[str, Any]]) -> list[WorkbenchNode]:
    if component_run is None:
        return []
    nodes = []
    for row in component_rows:
        component_id = int(row["component_id"])
        coverage_score = _optional_int(row.get("coverage_score"))
        exploration = _optional_int(row.get("exploration_priority_score"))
        changed = int(row.get("changed_node_count") or 0)
        candidates = _candidates(row)
        node_id = f"coverage-component-gap:{component_run['id']}:{component_id}"
        nodes.append(
            WorkbenchNode(
                id=node_id,
                entity_key=node_id,
                node_type="component_coverage_gap",
                label=f"Component {component_id} coverage",
                caption=f"coverage {coverage_score} · {changed} changed · {len(candidates)} suggested contexts",
                properties={
                    "analysis_run_id": str(component_run["id"]),
                    "snapshot_id": str(component_run["snapshot_id"]),
                    "component_id": component_id,
                    "coverage_score": coverage_score,
                    "exploration_priority_score": exploration,
                    "changed_node_count": changed,
                    "coverage_is_verdict": False,
                },
                metadata={"signals": _component_signals(row), "coverage_contract": _coverage_signal_contract()},
                badges=["component_gap", "coverage_signal"],
                metrics={"coverage_signal": coverage_score, "exploration_pressure": exploration, "changed_node_count": changed},
                evidence_refs=[_component_ref(component_run, component_id)],
                action_affordance_count=len(candidates),
                staleness="fresh" if changed else "unknown",
                confidence=(float(exploration or 0) / 100.0) if exploration is not None else 0.5,
                source_refs=[_component_ref(component_run, component_id)],
            )
        )
    return nodes


def _suggested_context_nodes(gap_node: WorkbenchNode, component_rows: list[Mapping[str, Any]]) -> list[WorkbenchNode]:
    component_id = gap_node.properties.get("component_id")
    analysis_run_id = gap_node.properties.get("analysis_run_id")
    row = next((row for row in component_rows if int(row["component_id"]) == component_id), None)
    if row is None:
        return []
    nodes = []
    for index, candidate in enumerate(_candidates(row)[:2]):
        capability, profile = _capability_key(candidate)
        rank_signal = _candidate_rank_signal(candidate)
        node_id = f"suggested-next-context:{analysis_run_id}:{component_id}:{index}"
        nodes.append(
            WorkbenchNode(
                id=node_id,
                entity_key=node_id,
                node_type="suggested_next_context",
                label=f"{capability} / {profile}",
                caption="candidate context, not direct action launch",
                properties={
                    "analysis_run_id": str(analysis_run_id),
                    "component_id": component_id,
                    "candidate_index": index,
                    "capability_id": capability,
                    "profile_id": profile,
                    "rank_signal": rank_signal,
                    "enabled_for_direct_execution": False,
                    "coverage_is_verdict": False,
                },
                metadata={"candidate": _candidate_summary(candidate), "coverage_contract": _coverage_signal_contract()},
                badges=["suggested_context", capability],
                metrics={"rank_signal": rank_signal} if rank_signal is not None else {},
                evidence_refs=gap_node.evidence_refs,
                staleness="unknown",
                confidence=float(rank_signal or 0) / 100.0 if rank_signal is not None else 0.5,
                source_refs=gap_node.source_refs,
            )
        )
    return nodes


def _coverage_row(row: Mapping[str, Any], checked_values: set[str], delta_by_subject: Mapping[str, str]) -> dict[str, Any]:
    surface_entity_key = _surface_entity_key(row)
    values = _target_values(row)
    checked = bool(checked_values.intersection(values))
    node_fingerprint = str(row["node_fingerprint"])
    delta_state = delta_by_subject.get(node_fingerprint, "unchanged")
    stale = _stale_surface_row(row, delta_state, checked=checked)
    return {
        "id": str(row["id"]),
        "node_type": str(row["node_type"]),
        "host": row.get("host"),
        "path": row.get("path"),
        "route_template": row.get("route_template"),
        "method": row.get("method"),
        "status_code": row.get("status_code"),
        "content_type": row.get("content_type"),
        "node_fingerprint": node_fingerprint,
        "feature_fingerprint": str(row["feature_fingerprint"]),
        "surface_entity_key": surface_entity_key,
        "checked": checked,
        "stale": stale,
        "delta_state": delta_state,
        "last_seen": row.get("last_seen"),
        "evidence_refs": _source_refs(row),
    }


def _checked_entity_values(action_rows: list[Mapping[str, Any]], outcome_rows: list[Mapping[str, Any]]) -> set[str]:
    values: set[str] = set()
    for row in action_rows:
        target = row.get("target")
        if target is not None:
            values.add(str(target))
    for row in outcome_rows:
        for key in ("node_id", "action_id", "run_id"):
            value = row.get(key)
            if value is not None:
                values.add(str(value))
    return values


def _target_values(row: Mapping[str, Any]) -> set[str]:
    host = _text(row.get("host"))
    path = _text(row.get("path"))
    route = _text(row.get("route_template"))
    method = _text(row.get("method"))
    values: list[object] = [
        _surface_entity_key(row),
        f"node:{row['id']}",
        row["id"],
        row["node_fingerprint"],
        row["feature_fingerprint"],
        host,
        path,
        route,
    ]
    for suffix in (path, route):
        if host and suffix:
            values.extend([f"{host}{suffix}", f"http://{host}{suffix}", f"https://{host}{suffix}"])
        if method and suffix:
            values.append(f"{method} {suffix}")
    return {text for value in values if (text := _text(value))}


def _component_gap_rows(items: list[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    selected = [
        row
        for row in items
        if _optional_int(row.get("coverage_score")) is None
        or int(row.get("coverage_score") or 0) < 60
        or int(row.get("changed_node_count") or 0) > 0
        or int(row.get("action_candidate_count") or 0) > 0
    ]
    return sorted(
        selected,
        key=lambda row: (
            int(row.get("coverage_score") or 0),
            -int(row.get("exploration_priority_score") or 0),
            -int(row.get("changed_node_count") or 0),
            int(row.get("component_id") or 0),
        ),
    )


def _sort_coverage_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: (
            0 if row["delta_state"] in {"added", "changed"} else 1,
            0 if row["node_type"] in {"endpoint", "route_template", "param"} else 1,
            0 if row["stale"] else 1,
            str(row.get("host") or ""),
            str(row.get("route_template") or row.get("path") or ""),
        ),
    )


def _coverage_edge(source: str, target: str, relationship_type: str, label: str, *, delta_state: str = "unchanged") -> WorkbenchEdge:
    return WorkbenchEdge(
        id=f"edge:{source}:{relationship_type}:{target}",
        source=source,
        target=target,
        relationship_type=relationship_type,
        label=label,
        confidence=1.0,
        delta_state=delta_state,
        source_projection="workbench_coverage",
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
    return [node for node in nodes if node.id in selected], [edge for edge in edges if edge.source in selected and edge.target in selected]


def _node_by_entity_key(graph: WorkbenchGraph, entity_key: str) -> WorkbenchNode | None:
    return next((node for node in graph.nodes if node.entity_key == entity_key), None)


def _related_actions_from_coverage_node(node: WorkbenchNode) -> list[dict[str, Any]]:
    if node.node_type not in {"capability_lane", "suggested_next_context"}:
        return []
    return [
        {
            "capability_id": node.properties.get("capability_id"),
            "profile_id": node.properties.get("profile_id"),
            "enabled": False,
            "reason": "coverage_lens_is_read_only",
        }
    ]


def _surface_entity_key(row: Mapping[str, Any]) -> str:
    return f"surface:{row['node_type']}:{row['node_fingerprint']}"


def _surface_label(row: Mapping[str, Any]) -> str:
    method = _text(row.get("method"))
    route = _text(row.get("route_template") or row.get("path"))
    host = _text(row.get("host"))
    if method and route:
        return f"{method} {route}"
    return route or host or str(row["node_type"])


def _surface_properties(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "surface_entity_key": row["surface_entity_key"],
        "node_type": row["node_type"],
        "host": row.get("host"),
        "path": row.get("path"),
        "route_template": row.get("route_template"),
        "method": row.get("method"),
        "status_code": row.get("status_code"),
        "node_fingerprint": row["node_fingerprint"],
        "feature_fingerprint": row["feature_fingerprint"],
        "delta_state": row["delta_state"],
        "stale": row["stale"],
    }


def _source_refs(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    if row.get("ref_type") and row.get("ref_id"):
        return [{"type": row["ref_type"], "id": str(row["ref_id"])}]
    return [{"type": "surface_node", "id": str(row["id"])}]


def _stale_surface_row(row: Mapping[str, Any], delta_state: str, *, checked: bool) -> bool:
    del row
    if delta_state == "removed":
        return True
    return not checked and delta_state == "unchanged"


def _component_signals(row: Mapping[str, Any]) -> dict[str, int | None]:
    return {
        "structural_pressure": _optional_int(row.get("structural_pressure_score")),
        "drift": _optional_int(row.get("drift_score")),
        "bridge_pressure": _optional_int(row.get("bridge_pressure_score")),
        "outlier": _optional_int(row.get("outlier_score")),
        "coverage": _optional_int(row.get("coverage_score")),
        "exploration_pressure": _optional_int(row.get("exploration_priority_score")),
    }


def _component_ref(run: Mapping[str, Any], component_id: int) -> dict[str, Any]:
    return {"type": "surface_component_analysis_item", "id": f"{run['id']}:{component_id}", "analysis_run_id": str(run["id"]), "component_id": component_id}


def _candidate_summary(candidate: Mapping[str, Any]) -> dict[str, Any]:
    capability, profile = _capability_key(candidate)
    return {
        "capability_id": capability,
        "profile_id": profile,
        "rank_signal": _candidate_rank_signal(candidate),
        "ranker_kind": candidate.get("ranker_kind") or "heuristic",
        "calibration_status": candidate.get("calibration_status") or "uncalibrated",
        "signal_features": candidate.get("score_features") or candidate.get("candidate_score_features") or {},
    }


def _candidate_rank_signal(candidate: Mapping[str, Any]) -> int | None:
    value = candidate.get("rank_signal")
    if value is None:
        value = candidate.get("candidate_score")
    if value is None:
        value = candidate.get("utility_score")
    return _optional_int(value)


def _capability_key(row: Mapping[str, Any]) -> tuple[str, str]:
    return (str(row.get("capability_id") or row.get("capability") or "unknown"), str(row.get("profile_id") or row.get("profile") or "default"))


def _capability_lane_id(capability: str, profile: str) -> str:
    return f"coverage-lane:capability:{_slug(capability)}:{_slug(profile)}"


def _candidates(row: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    candidates = row.get("action_candidates_json") or []
    return [candidate for candidate in candidates if isinstance(candidate, Mapping)]


def _coverage_signal_contract() -> dict[str, str]:
    return {
        "kind": "deterministic_read_model",
        "calibration_status": "uncalibrated",
        "not_semantics": "vulnerability/risk/severity/finding/verdict",
    }


def _ratio(part: int, total: int) -> float:
    return float(part) / float(total) if total else 0.0


def _optional_int(value: object) -> int | None:
    return int(value) if value is not None else None


def _text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _slug(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value).strip("-") or "unknown"


def _iso(value: object) -> str | None:
    if value is None:
        return None
    isoformat = getattr(value, "isoformat", None)
    return isoformat() if callable(isoformat) else str(value)
