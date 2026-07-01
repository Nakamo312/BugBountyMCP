"""Surface component lens read-model for the dashboard workbench."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import bindparam, desc, select

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
from api.infrastructure.adapters.orm import surface_component_analysis_items, surface_component_analysis_runs

_COMPONENT_ITEM_COLUMNS = (
    surface_component_analysis_items.c.component_id,
    surface_component_analysis_items.c.node_count,
    surface_component_analysis_items.c.changed_node_count,
    surface_component_analysis_items.c.structural_pressure_score,
    surface_component_analysis_items.c.drift_score,
    surface_component_analysis_items.c.bridge_pressure_score,
    surface_component_analysis_items.c.outlier_score,
    surface_component_analysis_items.c.coverage_score,
    surface_component_analysis_items.c.exploration_priority_score,
    surface_component_analysis_items.c.action_candidate_count,
    surface_component_analysis_items.c.metrics_json,
    surface_component_analysis_items.c.action_candidates_json,
)


async def build_component_lens_graph(
    session_factory: Any,
    *,
    program_id: UUID,
    seed: str | None = None,
    depth: int = 1,
    limit: int = 250,
) -> WorkbenchGraph | None:
    async with session_factory() as session:
        run = await _latest_component_analysis(session, program_id)
        if run is None:
            return None
        item_rows = await _component_items_for_run(session, run["id"], limit=max(1, min(limit, 500)))

    nodes, edges = _component_graph_from_rows(program_id=program_id, run=run, items=item_rows, seed=seed)
    selected_nodes = nodes[:limit]
    selected_node_ids = {node.id for node in selected_nodes}
    selected_edges = [edge for edge in edges if edge.source in selected_node_ids and edge.target in selected_node_ids]
    return WorkbenchGraph(
        program_id=program_id,
        lens=WorkbenchLens.COMPONENTS,
        snapshot_id=run["snapshot_id"],
        seed=seed,
        depth=depth,
        nodes=selected_nodes,
        edges=selected_edges,
        counts={
            "nodes": len(selected_nodes),
            "edges": len(selected_edges),
            "components": len(item_rows),
            "action_candidates": sum(int(row.get("action_candidate_count") or 0) for row in item_rows),
            "changed_components": sum(1 for row in item_rows if int(row.get("changed_node_count") or 0) > 0),
        },
        boundary=workbench_read_boundary(surface="surface_component_lens_graph"),
    )


async def component_entity_profile(
    session_factory: Any,
    *,
    program_id: UUID,
    entity_key: str,
) -> WorkbenchEntityProfile | None:
    async with session_factory() as session:
        run = await _latest_component_analysis(session, program_id)
        if run is None:
            return None
        item = await _component_item_for_entity(session, run["id"], entity_key)
        if item is None:
            return None
    component_id = int(item["component_id"])
    node = _component_node_from_row(run, item)
    return WorkbenchEntityProfile(
        program_id=program_id,
        entity_key=node.entity_key,
        profile={
            "node_id": node.id,
            "node_type": node.node_type,
            "label": node.label,
            "caption": node.caption,
            "analysis_run_id": str(run["id"]),
            "snapshot_id": str(run["snapshot_id"]),
            "component_id": component_id,
        },
        properties=node.properties,
        evidence_refs=node.evidence_refs,
        related_actions=[_component_candidate_summary(candidate, index) for index, candidate in enumerate(_candidates(item))],
        memory_pointers=[_component_ref(run, component_id)],
        boundary=workbench_read_boundary(surface="surface_component_entity_profile"),
    )


async def component_entity_actions(
    session_factory: Any,
    *,
    program_id: UUID,
    entity_key: str,
    limit: int = 10,
) -> WorkbenchActionAffordanceList | None:
    async with session_factory() as session:
        run = await _latest_component_analysis(session, program_id)
        if run is None:
            return None
        item = await _component_item_for_entity(session, run["id"], entity_key)
        if item is None:
            return None
    return WorkbenchActionAffordanceList(
        program_id=program_id,
        entity_key=_component_entity_key(run, int(item["component_id"])),
        actions=[
            _component_candidate_affordance(candidate, index)
            for index, candidate in enumerate(_candidates(item)[: max(1, min(limit, 25))])
        ],
        boundary=workbench_read_boundary(surface="surface_component_action_candidates"),
    )


async def component_entity_memory(
    session_factory: Any,
    *,
    program_id: UUID,
    entity_key: str,
) -> WorkbenchEntityMemory | None:
    async with session_factory() as session:
        run = await _latest_component_analysis(session, program_id)
        if run is None:
            return None
        item = await _component_item_for_entity(session, run["id"], entity_key)
        if item is None:
            return None
    component_id = int(item["component_id"])
    return WorkbenchEntityMemory(
        program_id=program_id,
        entity_key=_component_entity_key(run, component_id),
        fragments=[_component_fragment(run, item)],
        tree_nodes=[_component_tree_node(run, item)],
        summaries=[_component_memory_summary(item)],
        evidence_refs=[_component_ref(run, component_id)],
        boundary=workbench_read_boundary(surface="surface_component_memory_from_analysis"),
    )


async def _latest_component_analysis(session: Any, program_id: UUID) -> Mapping[str, Any] | None:
    statement = (
        select(
            surface_component_analysis_runs.c.id,
            surface_component_analysis_runs.c.program_id,
            surface_component_analysis_runs.c.snapshot_id,
            surface_component_analysis_runs.c.previous_snapshot_id,
            surface_component_analysis_runs.c.algorithm,
            surface_component_analysis_runs.c.algorithm_version,
            surface_component_analysis_runs.c.report_fingerprint,
            surface_component_analysis_runs.c.stats_json,
            surface_component_analysis_runs.c.settings_json,
            surface_component_analysis_runs.c.created_at,
        )
        .where(surface_component_analysis_runs.c.program_id == bindparam("program_id"))
        .order_by(surface_component_analysis_runs.c.created_at.desc(), surface_component_analysis_runs.c.id.desc())
        .limit(1)
    )
    result = await session.execute(statement, {"program_id": program_id})
    return result.mappings().one_or_none()


async def _component_items_for_run(session: Any, analysis_run_id: UUID, *, limit: int) -> list[Mapping[str, Any]]:
    statement = (
        select(*_COMPONENT_ITEM_COLUMNS)
        .where(surface_component_analysis_items.c.analysis_run_id == bindparam("analysis_run_id"))
        .order_by(
            desc(surface_component_analysis_items.c.exploration_priority_score).nulls_last(),
            desc(surface_component_analysis_items.c.structural_pressure_score).nulls_last(),
            surface_component_analysis_items.c.component_id.asc(),
        )
        .limit(max(limit, 1))
    )
    result = await session.execute(statement, {"analysis_run_id": analysis_run_id})
    return list(result.mappings().all())


async def _component_item_for_entity(session: Any, analysis_run_id: UUID, entity_key: str) -> Mapping[str, Any] | None:
    component_id = _component_id_from_entity_key(entity_key)
    if component_id is None:
        return None
    statement = (
        select(*_COMPONENT_ITEM_COLUMNS)
        .where(surface_component_analysis_items.c.analysis_run_id == bindparam("analysis_run_id"))
        .where(surface_component_analysis_items.c.component_id == bindparam("component_id"))
        .limit(1)
    )
    result = await session.execute(statement, {"analysis_run_id": analysis_run_id, "component_id": component_id})
    return result.mappings().one_or_none()


def _component_graph_from_rows(
    *,
    program_id: UUID,
    run: Mapping[str, Any],
    items: list[Mapping[str, Any]],
    seed: str | None,
) -> tuple[list[WorkbenchNode], list[WorkbenchEdge]]:
    del program_id
    analysis_node = _analysis_node_from_row(run, items)
    component_nodes = [_component_node_from_row(run, row) for row in items]
    candidate_nodes: list[WorkbenchNode] = []
    edges: list[WorkbenchEdge] = []
    for row in items:
        component_id = int(row["component_id"])
        component_node_id = _component_node_id(run, component_id)
        edges.append(_component_edge(_analysis_node_id(run), component_node_id, "HAS_COMPONENT", "has component"))
        for index, candidate in enumerate(_candidates(row)):
            candidate_node = _candidate_node_from_payload(run, component_id, index, candidate)
            candidate_nodes.append(candidate_node)
            edges.append(_component_edge(component_node_id, candidate_node.id, "SUGGESTS_ACTION", "suggests action"))
    nodes = [analysis_node, *component_nodes, *candidate_nodes]
    if seed:
        selected_ids = _component_seed_ids(nodes, edges, seed)
        nodes = [node for node in nodes if node.id in selected_ids or node.entity_key in selected_ids]
        valid_ids = {node.id for node in nodes}
        edges = [edge for edge in edges if edge.source in valid_ids and edge.target in valid_ids]
    return nodes, edges


def _analysis_node_from_row(run: Mapping[str, Any], items: list[Mapping[str, Any]]) -> WorkbenchNode:
    stats = _dict(run.get("stats_json"))
    return WorkbenchNode(
        id=_analysis_node_id(run),
        entity_key=f"surface-component-analysis:{run['id']}",
        node_type="surface_component_analysis_run",
        label="Surface component analysis",
        caption=f"{len(items)} components · {run['algorithm_version']}",
        properties={
            "analysis_run_id": str(run["id"]),
            "snapshot_id": str(run["snapshot_id"]),
            "previous_snapshot_id": _str_or_none(run.get("previous_snapshot_id")),
            "algorithm": run.get("algorithm"),
            "algorithm_version": run.get("algorithm_version"),
            "report_fingerprint": run.get("report_fingerprint"),
            "created_at": _iso(run.get("created_at")),
        },
        metadata={"stats": stats, "signal_contract": _component_signal_contract()},
        badges=["analysis", "materialized"],
        metrics={"component_count": len(items), "action_candidate_count": sum(len(_candidates(row)) for row in items)},
        evidence_refs=[{"type": "surface_component_analysis_run", "id": str(run["id"])}],
        staleness="fresh",
        confidence=1.0,
        source_refs=[{"type": "surface_component_analysis_run", "id": str(run["id"])}],
    )


def _component_node_from_row(run: Mapping[str, Any], row: Mapping[str, Any]) -> WorkbenchNode:
    component_id = int(row["component_id"])
    signals = _component_signals(row)
    max_signal = max((value for value in signals.values() if isinstance(value, int)), default=0)
    return WorkbenchNode(
        id=_component_node_id(run, component_id),
        entity_key=_component_entity_key(run, component_id),
        node_type="surface_component",
        label=f"Component {component_id}",
        caption=f"{row['node_count']} nodes · {row['changed_node_count']} changed · {row['action_candidate_count']} candidates",
        properties={
            "analysis_run_id": str(run["id"]),
            "snapshot_id": str(run["snapshot_id"]),
            "component_id": component_id,
            "node_count": int(row["node_count"]),
            "changed_node_count": int(row["changed_node_count"]),
            "action_candidate_count": int(row["action_candidate_count"]),
        },
        metadata={"signals": signals, "metrics": _dict(row.get("metrics_json")), "signal_contract": _component_signal_contract()},
        badges=_component_badges(row),
        metrics={"signals": signals, "node_count": int(row["node_count"]), "changed_node_count": int(row["changed_node_count"])},
        evidence_refs=[_component_ref(run, component_id)],
        action_affordance_count=int(row["action_candidate_count"]),
        staleness="fresh" if int(row["changed_node_count"] or 0) else "unchanged",
        confidence=max_signal / 100 if max_signal else 0.5,
        source_refs=[_component_ref(run, component_id)],
    )


def _candidate_node_from_payload(
    run: Mapping[str, Any],
    component_id: int,
    index: int,
    candidate: Mapping[str, Any],
) -> WorkbenchNode:
    capability = str(candidate.get("capability_id") or candidate.get("capability") or "unknown")
    profile = str(candidate.get("profile_id") or candidate.get("profile") or "default")
    rank_signal = _candidate_rank_signal(candidate)
    return WorkbenchNode(
        id=_candidate_node_id(run, component_id, index),
        entity_key=f"surface-component-candidate:{run['id']}:{component_id}:{index}",
        node_type="surface_component_action_candidate",
        label=f"{capability} / {profile}",
        caption="backend materialized candidate signal",
        properties={
            "analysis_run_id": str(run["id"]),
            "component_id": component_id,
            "capability_id": capability,
            "profile_id": profile,
            "rank_signal": rank_signal,
            "ranker_kind": candidate.get("ranker_kind") or "heuristic",
            "calibration_status": candidate.get("calibration_status") or "uncalibrated",
        },
        metadata={"candidate": _component_candidate_summary(candidate, index)},
        badges=["candidate", capability, profile],
        metrics={"rank_signal": rank_signal} if rank_signal is not None else {},
        evidence_refs=[_component_ref(run, component_id)],
        staleness="unknown",
        confidence=float(rank_signal or 0) / 100 if rank_signal is not None else 0.5,
        source_refs=[_component_ref(run, component_id)],
    )


def _component_edge(source: str, target: str, relationship_type: str, label: str) -> WorkbenchEdge:
    return WorkbenchEdge(
        id=f"edge:{source}:{relationship_type}:{target}",
        source=source,
        target=target,
        relationship_type=relationship_type,
        label=label,
        confidence=1.0,
        delta_state="unchanged",
        source_projection="surface_component_analysis",
    )


def _component_seed_ids(nodes: list[WorkbenchNode], edges: list[WorkbenchEdge], seed: str) -> set[str]:
    seed_node_ids = {node.id for node in nodes if seed in {node.id, node.entity_key}}
    if not seed_node_ids:
        return set()
    selected = set(seed_node_ids)
    for edge in edges:
        if edge.source in seed_node_ids:
            selected.add(edge.target)
        if edge.target in seed_node_ids:
            selected.add(edge.source)
    return selected


def _component_signals(row: Mapping[str, Any]) -> dict[str, int | None]:
    return {
        "structural_pressure": _optional_int(row.get("structural_pressure_score")),
        "drift": _optional_int(row.get("drift_score")),
        "bridge_pressure": _optional_int(row.get("bridge_pressure_score")),
        "outlier": _optional_int(row.get("outlier_score")),
        "coverage": _optional_int(row.get("coverage_score")),
        "exploration_pressure": _optional_int(row.get("exploration_priority_score")),
    }


def _component_signal_contract() -> dict[str, str]:
    return {
        "kind": "heuristic",
        "calibration_status": "uncalibrated",
        "not_semantics": "priority/severity/risk/learned_utility",
    }


def _component_badges(row: Mapping[str, Any]) -> list[str]:
    badges = ["component"]
    if int(row.get("changed_node_count") or 0) > 0:
        badges.append("changed")
    if int(row.get("action_candidate_count") or 0) > 0:
        badges.append("has candidates")
    return badges


def _component_candidate_affordance(candidate: Mapping[str, Any], index: int) -> WorkbenchActionAffordance:
    capability = str(candidate.get("capability_id") or candidate.get("capability") or "unknown")
    profile = str(candidate.get("profile_id") or candidate.get("profile") or "default")
    return WorkbenchActionAffordance(
        catalog_id=f"{capability}.{profile}",
        label=f"{capability} / {profile}",
        profile=profile,
        enabled=False,
        disabled_reasons=["candidate_only_requires_action_service_submission"],
        policy_preview={
            "candidate_index": index,
            "ranker_kind": candidate.get("ranker_kind") or "heuristic",
            "calibration_status": candidate.get("calibration_status") or "uncalibrated",
            "formula_version": candidate.get("score_formula_version") or candidate.get("formula_version"),
        },
        expected_delta=[_candidate_expected_delta(candidate)],
        prior_outcomes=[],
    )


def _component_candidate_summary(candidate: Mapping[str, Any], index: int) -> dict[str, Any]:
    return {
        "candidate_index": index,
        "capability_id": candidate.get("capability_id") or candidate.get("capability") or "unknown",
        "profile_id": candidate.get("profile_id") or candidate.get("profile") or "default",
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


def _candidate_expected_delta(candidate: Mapping[str, Any]) -> dict[str, Any]:
    features = candidate.get("score_features") or candidate.get("candidate_score_features") or {}
    return {"kind": "candidate_signal_features", "features": features} if isinstance(features, dict) else {"kind": "candidate_signal"}


def _component_fragment(run: Mapping[str, Any], row: Mapping[str, Any]) -> dict[str, Any]:
    component_id = int(row["component_id"])
    return {
        "kind": "surface_component_analysis_item",
        "id": f"{run['id']}:{component_id}",
        "analysis_run_id": str(run["id"]),
        "snapshot_id": str(run["snapshot_id"]),
        "component_id": component_id,
        "node_count": int(row["node_count"]),
        "changed_node_count": int(row["changed_node_count"]),
        "signals": _component_signals(row),
        "action_candidates": [_component_candidate_summary(candidate, index) for index, candidate in enumerate(_candidates(row))],
        "created_at": _iso(run.get("created_at")),
    }


def _component_tree_node(run: Mapping[str, Any], row: Mapping[str, Any]) -> dict[str, Any]:
    component_id = int(row["component_id"])
    return {
        "id": f"component:{run['id']}:{component_id}",
        "kind": "surface_component",
        "parent_id": f"analysis:{run['id']}",
        "label": f"Component {component_id}",
        "evidence_ref": _component_ref(run, component_id),
        "created_at": _iso(run.get("created_at")),
    }


def _component_memory_summary(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "kind": "surface_component_signal_summary",
        "node_count": int(row["node_count"]),
        "changed_node_count": int(row["changed_node_count"]),
        "action_candidate_count": int(row["action_candidate_count"]),
        "signals": _component_signals(row),
        "signal_contract": _component_signal_contract(),
    }


def _component_ref(run: Mapping[str, Any], component_id: int) -> dict[str, Any]:
    return {
        "type": "surface_component_analysis_item",
        "id": f"{run['id']}:{component_id}",
        "analysis_run_id": str(run["id"]),
        "component_id": component_id,
    }


def _analysis_node_id(run: Mapping[str, Any]) -> str:
    return f"analysis:{run['id']}"


def _component_node_id(run: Mapping[str, Any], component_id: int) -> str:
    return f"component:{run['id']}:{component_id}"


def _candidate_node_id(run: Mapping[str, Any], component_id: int, index: int) -> str:
    return f"candidate:{run['id']}:{component_id}:{index}"


def _component_entity_key(run: Mapping[str, Any], component_id: int) -> str:
    return f"surface-component:{run['id']}:{component_id}"


def _is_component_entity_key(entity_key: str) -> bool:
    return entity_key.startswith("surface-component:") or entity_key.startswith("surface-component-candidate:")


def _component_id_from_entity_key(entity_key: str) -> int | None:
    parts = entity_key.split(":")
    if entity_key.startswith("surface-component:") and len(parts) >= 3:
        raw = parts[2]
    elif entity_key.startswith("surface-component-candidate:") and len(parts) >= 4:
        raw = parts[2]
    else:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _candidates(row: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    candidates = row.get("action_candidates_json") or []
    return [candidate for candidate in candidates if isinstance(candidate, Mapping)]


def _optional_int(value: object) -> int | None:
    return int(value) if value is not None else None


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _str_or_none(value: object) -> str | None:
    return str(value) if value is not None else None


def _iso(value: object) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else _str_or_none(value)
