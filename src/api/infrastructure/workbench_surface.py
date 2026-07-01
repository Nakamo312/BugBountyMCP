"""Surface lens and surface-entity read model for the dashboard workbench."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import bindparam, desc, func, select

from api.application.workbench import (
    WorkbenchActionAffordanceList,
    WorkbenchEdge,
    WorkbenchEntityMemory,
    WorkbenchEntityProfile,
    WorkbenchGraph,
    WorkbenchLens,
    WorkbenchNode,
    workbench_read_boundary,
)
from api.infrastructure.adapters.orm import surface_deltas, surface_edges, surface_nodes, surface_snapshots
from api.infrastructure.workbench_action_rows import (
    _action_affordance,
    _action_summary,
    _actions_for_entity,
    _artifact_ref,
    _artifacts_for_outcomes,
    _dedupe_dicts,
    _memory_pointers,
    _outcome_fragment,
    _outcome_ref,
    _outcome_summary,
    _outcomes_by_action,
    _outcomes_for_entity,
)
from api.infrastructure.workbench_memory import build_entity_memory_summaries, build_entity_memory_tree

_NODE_COLUMNS = (
    surface_nodes.c.id,
    surface_nodes.c.node_type,
    surface_nodes.c.ref_type,
    surface_nodes.c.ref_id,
    surface_nodes.c.node_fingerprint,
    surface_nodes.c.feature_fingerprint,
    surface_nodes.c.host,
    surface_nodes.c.path,
    surface_nodes.c.route_template,
    surface_nodes.c.method,
    surface_nodes.c.status_code,
    surface_nodes.c.content_type,
    surface_nodes.c.features_json,
    surface_nodes.c.safe_for_search,
    surface_nodes.c.first_seen,
    surface_nodes.c.last_seen,
)

_EDGE_COLUMNS = (
    surface_edges.c.id,
    surface_edges.c.src_node_id,
    surface_edges.c.dst_node_id,
    surface_edges.c.edge_type,
    surface_edges.c.weight,
    surface_edges.c.edge_fingerprint,
    surface_edges.c.evidence_json,
    surface_edges.c.created_at,
)



async def build_surface_lens_graph(
    session_factory,
    *,
    program_id: UUID,
    seed: str | None = None,
    depth: int = 1,
    limit: int = 250,
) -> WorkbenchGraph | None:
    async with session_factory() as session:
        snapshot = await _latest_snapshot(session, program_id)
        if snapshot is None:
            return None
        node_rows = await _nodes_for_snapshot(session, program_id, snapshot["id"], limit=limit)
        edge_rows = await _edges_for_snapshot(session, program_id, snapshot["id"])
        delta_by_subject = await _deltas_for_snapshot(session, program_id, snapshot["id"])

    if seed:
        node_rows, edge_rows = _neighborhood(node_rows, edge_rows, seed=seed, depth=depth, limit=limit)
    else:
        node_ids = {row["id"] for row in node_rows[:limit]}
        node_rows = node_rows[:limit]
        edge_rows = [row for row in edge_rows if row["src_node_id"] in node_ids and row["dst_node_id"] in node_ids]

    nodes = [_node_from_row(row, delta_by_subject) for row in node_rows]
    valid_node_ids = {node.id for node in nodes}
    edges = [
        _edge_from_row(row, delta_by_subject)
        for row in edge_rows
        if _node_id(row["src_node_id"]) in valid_node_ids and _node_id(row["dst_node_id"]) in valid_node_ids
    ]
    return WorkbenchGraph(
        program_id=program_id,
        lens=WorkbenchLens.SURFACE,
        snapshot_id=snapshot["id"],
        seed=seed,
        depth=depth,
        nodes=nodes,
        edges=edges,
        counts={
            "nodes": len(nodes),
            "edges": len(edges),
            "snapshot_nodes_total": int(snapshot.get("node_count") or 0),
            "snapshot_edges_total": int(snapshot.get("edge_count") or 0),
        },
        boundary=workbench_read_boundary(surface="surface_lens_graph"),
    )


async def surface_entity_profile(session_factory, *, program_id: UUID, entity_key: str) -> WorkbenchEntityProfile | None:
    async with session_factory() as session:
        snapshot = await _latest_snapshot(session, program_id)
        if snapshot is None:
            return None
        row = await _entity_node(session, program_id, snapshot["id"], entity_key)
        if row is None:
            return None
        deltas = await _deltas_for_snapshot(session, program_id, snapshot["id"])
        actions = await _actions_for_entity(session, program_id, _target_values(row), limit=5)
        outcomes = await _outcomes_for_entity(
            session,
            program_id,
            _target_values(row),
            [action["action_id"] for action in actions],
            limit=5,
        )
    node = _node_from_row(row, deltas)
    return WorkbenchEntityProfile(
        program_id=program_id,
        entity_key=node.entity_key,
        profile={
            "node_id": node.id,
            "node_type": node.node_type,
            "label": node.label,
            "caption": node.caption,
            "snapshot_id": str(snapshot["id"]),
        },
        properties=node.properties,
        evidence_refs=node.evidence_refs,
        related_outcomes=[_outcome_summary(row) for row in outcomes],
        related_actions=[_action_summary(row) for row in actions],
        memory_pointers=[*node.source_refs, *_memory_pointers(outcomes)],
        boundary=workbench_read_boundary(surface="surface_entity_profile"),
    )


async def surface_entity_actions(
    session_factory,
    *,
    program_id: UUID,
    entity_key: str,
    limit: int = 10,
) -> WorkbenchActionAffordanceList | None:
    async with session_factory() as session:
        snapshot = await _latest_snapshot(session, program_id)
        if snapshot is None:
            return None
        row = await _entity_node(session, program_id, snapshot["id"], entity_key)
        if row is None:
            return None
        actions = await _actions_for_entity(session, program_id, _target_values(row), limit=max(1, min(limit, 25)))
        action_ids = [action["action_id"] for action in actions]
        outcomes = await _outcomes_for_entity(session, program_id, _target_values(row), action_ids, limit=25)

    outcomes_by_action = _outcomes_by_action(outcomes)
    return WorkbenchActionAffordanceList(
        program_id=program_id,
        entity_key=_entity_key(row),
        actions=[_action_affordance(row, outcomes_by_action.get(row["action_id"], [])) for row in actions],
        boundary=workbench_read_boundary(surface="contextual_actions_from_history"),
    )


async def surface_entity_memory(
    session_factory,
    *,
    program_id: UUID,
    entity_key: str,
    limit: int = 20,
) -> WorkbenchEntityMemory | None:
    async with session_factory() as session:
        snapshot = await _latest_snapshot(session, program_id)
        if snapshot is None:
            return None
        row = await _entity_node(session, program_id, snapshot["id"], entity_key)
        if row is None:
            return None
        targets = _target_values(row)
        actions = await _actions_for_entity(session, program_id, targets, limit=25)
        outcomes = await _outcomes_for_entity(
            session,
            program_id,
            targets,
            [action["action_id"] for action in actions],
            limit=max(1, min(limit, 50)),
        )
        artifacts = await _artifacts_for_outcomes(
            session,
            [outcome["run_id"] for outcome in outcomes],
            program_id=program_id,
            limit=50,
        )

    node = _node_from_row(row, {})
    evidence_refs = [*node.evidence_refs, *[_outcome_ref(outcome) for outcome in outcomes], *[_artifact_ref(row) for row in artifacts]]
    return WorkbenchEntityMemory(
        program_id=program_id,
        entity_key=node.entity_key,
        fragments=[_outcome_fragment(outcome) for outcome in outcomes],
        tree_nodes=build_entity_memory_tree(outcomes),
        summaries=build_entity_memory_summaries(outcomes, artifacts),
        evidence_refs=_dedupe_dicts(evidence_refs),
        boundary=workbench_read_boundary(surface="entity_memory_from_action_outcomes"),
    )


def _target_values(row: Mapping[str, Any]) -> list[str]:
    host = _text(row.get("host"))
    path = _text(row.get("path"))
    route = _text(row.get("route_template"))
    method = _text(row.get("method"))
    values = [
        _entity_key(row),
        _node_id(row["id"]),
        str(row["id"]),
        str(row["node_fingerprint"]),
        str(row["feature_fingerprint"]),
        host,
        path,
        route,
    ]
    for suffix in (path, route):
        if host and suffix:
            values.extend([f"{host}{suffix}", f"http://{host}{suffix}", f"https://{host}{suffix}"])
        if method and suffix:
            values.append(f"{method} {suffix}")
    return _unique_text(values)


def _unique_text(values: list[object]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = _text(value)
        if text is None or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


async def _latest_snapshot(session: Any, program_id: UUID) -> Mapping[str, Any] | None:
    node_count = (
        select(func.count())
        .select_from(surface_nodes)
        .where(surface_nodes.c.snapshot_id == surface_snapshots.c.id)
        .scalar_subquery()
    )
    edge_count = (
        select(func.count())
        .select_from(surface_edges)
        .where(surface_edges.c.snapshot_id == surface_snapshots.c.id)
        .scalar_subquery()
    )
    statement = (
        select(
            surface_snapshots.c.id,
            surface_snapshots.c.snapshot_fingerprint,
            surface_snapshots.c.created_at,
            surface_snapshots.c.source_window_end,
            node_count.label("node_count"),
            edge_count.label("edge_count"),
        )
        .where(surface_snapshots.c.program_id == bindparam("program_id"))
        .order_by(surface_snapshots.c.created_at.desc(), surface_snapshots.c.id.desc())
        .limit(1)
    )
    result = await session.execute(statement, {"program_id": program_id})
    return result.mappings().one_or_none()


async def _nodes_for_snapshot(session: Any, program_id: UUID, snapshot_id: UUID, *, limit: int) -> list[Mapping[str, Any]]:
    statement = (
        select(*_NODE_COLUMNS)
        .where(surface_nodes.c.program_id == bindparam("program_id"))
        .where(surface_nodes.c.snapshot_id == bindparam("snapshot_id"))
        .order_by(surface_nodes.c.node_type.asc(), surface_nodes.c.host.asc(), surface_nodes.c.route_template.asc())
        .limit(max(limit, 1))
    )
    result = await session.execute(statement, {"program_id": program_id, "snapshot_id": snapshot_id})
    return list(result.mappings().all())


async def _edges_for_snapshot(session: Any, program_id: UUID, snapshot_id: UUID) -> list[Mapping[str, Any]]:
    statement = (
        select(*_EDGE_COLUMNS)
        .where(surface_edges.c.program_id == bindparam("program_id"))
        .where(surface_edges.c.snapshot_id == bindparam("snapshot_id"))
        .order_by(surface_edges.c.edge_type.asc(), surface_edges.c.id.asc())
    )
    result = await session.execute(statement, {"program_id": program_id, "snapshot_id": snapshot_id})
    return list(result.mappings().all())


async def _entity_node(session: Any, program_id: UUID, snapshot_id: UUID, entity_key: str) -> Mapping[str, Any] | None:
    fingerprint = _fingerprint_from_seed(entity_key)
    node_uuid = _uuid_from_seed(entity_key)
    predicates = [
        surface_nodes.c.node_fingerprint == bindparam("fingerprint"),
        surface_nodes.c.feature_fingerprint == bindparam("fingerprint"),
    ]
    parameters: dict[str, object] = {"program_id": program_id, "snapshot_id": snapshot_id, "fingerprint": fingerprint}
    if node_uuid is not None:
        predicates.append(surface_nodes.c.id == bindparam("node_uuid"))
        parameters["node_uuid"] = node_uuid
    statement = (
        select(*_NODE_COLUMNS)
        .where(surface_nodes.c.program_id == bindparam("program_id"))
        .where(surface_nodes.c.snapshot_id == bindparam("snapshot_id"))
        .where(or_(*predicates))
        .limit(1)
    )
    result = await session.execute(statement, parameters)
    return result.mappings().one_or_none()


async def _deltas_for_snapshot(session: Any, program_id: UUID, snapshot_id: UUID) -> dict[str, str]:
    statement = (
        select(surface_deltas.c.subject_fingerprint, surface_deltas.c.delta_type)
        .where(surface_deltas.c.program_id == bindparam("program_id"))
        .where(surface_deltas.c.to_snapshot_id == bindparam("snapshot_id"))
    )
    result = await session.execute(statement, {"program_id": program_id, "snapshot_id": snapshot_id})
    return {str(row["subject_fingerprint"]): _delta_state(row["delta_type"]) for row in result.mappings().all()}


def _neighborhood(
    node_rows: list[Mapping[str, Any]],
    edge_rows: list[Mapping[str, Any]],
    *,
    seed: str,
    depth: int,
    limit: int,
) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]]]:
    nodes_by_id = {row["id"]: row for row in node_rows}
    seed_ids = {row["id"] for row in node_rows if _matches_seed(row, seed)}
    if not seed_ids:
        return [], []

    selected = set(seed_ids)
    frontier = set(seed_ids)
    for _ in range(max(0, depth)):
        next_frontier: set[UUID] = set()
        for edge in edge_rows:
            src = edge["src_node_id"]
            dst = edge["dst_node_id"]
            if src in frontier and dst not in selected:
                next_frontier.add(dst)
            if dst in frontier and src not in selected:
                next_frontier.add(src)
        if not next_frontier:
            break
        selected.update(next_frontier)
        frontier = next_frontier
        if len(selected) >= limit:
            selected = set(list(selected)[:limit])
            break

    selected_edges = [edge for edge in edge_rows if edge["src_node_id"] in selected and edge["dst_node_id"] in selected]
    selected_nodes = [row for node_id, row in nodes_by_id.items() if node_id in selected]
    return selected_nodes[:limit], selected_edges


def _node_from_row(row: Mapping[str, Any], delta_by_subject: Mapping[str, str]) -> WorkbenchNode:
    features = dict(row["features_json"] or {}) if row.get("safe_for_search") else {}
    label = _node_label(row, features)
    source_refs = _source_refs(row, features)
    node_fingerprint = str(row["node_fingerprint"])
    return WorkbenchNode(
        id=_node_id(row["id"]),
        entity_key=_entity_key(row),
        node_type=str(row["node_type"]),
        label=label,
        caption=_node_caption(row, features),
        properties={
            "host": row.get("host"),
            "path": row.get("path"),
            "route_template": row.get("route_template"),
            "method": row.get("method"),
            "status_code": row.get("status_code"),
            "content_type": row.get("content_type"),
            "feature_fingerprint": str(row["feature_fingerprint"]),
            "node_fingerprint": node_fingerprint,
        },
        metadata={"features": features},
        badges=_node_badges(row),
        evidence_refs=source_refs,
        staleness=_staleness(row, delta_by_subject.get(node_fingerprint)),
        confidence=1.0 if row.get("safe_for_search") else 0.5,
        source_refs=source_refs,
    )


def _edge_from_row(row: Mapping[str, Any], delta_by_subject: Mapping[str, str]) -> WorkbenchEdge:
    edge_fingerprint = str(row["edge_fingerprint"])
    return WorkbenchEdge(
        id=f"edge:{row['id']}",
        source=_node_id(row["src_node_id"]),
        target=_node_id(row["dst_node_id"]),
        relationship_type=str(row["edge_type"]),
        label=_edge_label(str(row["edge_type"])),
        weight=float(row["weight"]),
        confidence=float(row["weight"]),
        evidence_refs=_edge_evidence(row),
        created_at=row.get("created_at"),
        delta_state=delta_by_subject.get(edge_fingerprint, "unchanged"),
        source_projection="surface_map",
    )


def _node_id(value: object) -> str:
    return f"node:{value}"


def _entity_key(row: Mapping[str, Any]) -> str:
    return f"surface:{row['node_type']}:{row['node_fingerprint']}"


def _matches_seed(row: Mapping[str, Any], seed: str) -> bool:
    values = {
        str(row["id"]),
        _node_id(row["id"]),
        str(row["node_fingerprint"]),
        str(row["feature_fingerprint"]),
        _entity_key(row),
    }
    return seed in values


def _fingerprint_from_seed(seed: str) -> str:
    if seed.startswith("surface:"):
        return seed.rsplit(":", 1)[-1]
    if seed.startswith("node:"):
        return seed.removeprefix("node:")
    return seed


def _uuid_from_seed(seed: str) -> UUID | None:
    value = seed.removeprefix("node:")
    try:
        return UUID(value)
    except ValueError:
        return None


def _node_label(row: Mapping[str, Any], features: Mapping[str, Any]) -> str:
    node_type = str(row["node_type"])
    method = _text(row.get("method") or features.get("method"))
    route = _text(row.get("route_template") or features.get("route_template") or row.get("path"))
    host = _text(row.get("host") or features.get("host"))
    if node_type in {"endpoint", "route_template"}:
        parts = [part for part in (method, route) if part]
        return " ".join(parts) if parts else host or node_type
    if node_type == "response_shape":
        status = _text(row.get("status_code") or features.get("status_family"))
        content_type = _text(row.get("content_type"))
        return " ".join(part for part in ("Response", status, content_type) if part)
    return host or route or node_type


def _node_caption(row: Mapping[str, Any], features: Mapping[str, Any]) -> str | None:
    bits = [
        _text(row.get("host")),
        _text(row.get("content_type")),
        _text(features.get("source", {}).get("source_tool") if isinstance(features.get("source"), dict) else None),
    ]
    return ", ".join(bit for bit in bits if bit) or None


def _node_badges(row: Mapping[str, Any]) -> list[str]:
    badges = [str(row["node_type"])]
    if row.get("method"):
        badges.append(str(row["method"]))
    if row.get("status_code"):
        badges.append(str(row["status_code"]))
    return badges


def _source_refs(row: Mapping[str, Any], features: Mapping[str, Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    if row.get("ref_type") and row.get("ref_id"):
        refs.append({"type": row["ref_type"], "id": str(row["ref_id"])})
    source = features.get("source")
    if isinstance(source, dict) and source.get("ref_type") and source.get("ref_id"):
        ref = {"type": source["ref_type"], "id": str(source["ref_id"])}
        if ref not in refs:
            refs.append(ref)
    return refs


def _edge_evidence(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    evidence = dict(row["evidence_json"] or {})
    return [{"type": "surface_edge", "payload": evidence}] if evidence else []


def _edge_label(edge_type: str) -> str:
    return edge_type.lower().replace("_", " ")


def _staleness(row: Mapping[str, Any], delta_state: str | None) -> str:
    if delta_state in {"added", "changed"}:
        return "fresh"
    if row.get("last_seen") is None:
        return "unknown"
    return "unchanged"


def _delta_state(delta_type: object) -> str:
    value = str(delta_type).lower()
    if "add" in value or "new" in value:
        return "added"
    if "remove" in value or "delete" in value or "missing" in value:
        return "removed"
    if "change" in value or "update" in value or "drift" in value:
        return "changed"
    return "changed"


def _text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


latest_surface_snapshot = _latest_snapshot
surface_nodes_for_snapshot = _nodes_for_snapshot
surface_deltas_for_snapshot = _deltas_for_snapshot
