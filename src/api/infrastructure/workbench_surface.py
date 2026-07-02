"""Surface lens and surface-entity read model for the dashboard workbench."""
from __future__ import annotations

from collections.abc import Mapping
import base64
import re
from typing import Any
from uuid import UUID

from sqlalchemy import bindparam, case, desc, func, or_, select

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
        node_rows = await _nodes_for_snapshot(
            session,
            program_id,
            snapshot["id"],
            limit=_surface_overview_fetch_limit(limit, seeded=bool(seed)),
        )
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
    ui_nodes: list[WorkbenchNode] = []
    ui_edges: list[WorkbenchEdge] = []
    if not edges and not seed and len(nodes) > 1:
        ui_nodes, ui_edges = _surface_ui_grouping(node_rows)

    return WorkbenchGraph(
        program_id=program_id,
        lens=WorkbenchLens.SURFACE,
        snapshot_id=snapshot["id"],
        seed=seed,
        depth=depth,
        nodes=[*ui_nodes, *nodes],
        edges=[*ui_edges, *edges],
        counts={
            "nodes": len(nodes),
            "edges": len(edges),
            "ui_group_nodes": len(ui_nodes),
            "ui_group_edges": len(ui_edges),
            "snapshot_nodes_total": int(snapshot.get("node_count") or 0),
            "snapshot_edges_total": int(snapshot.get("edge_count") or 0),
        },
        boundary={
            **workbench_read_boundary(surface="surface_lens_graph"),
            "ui_grouping": "derived_from_surface_node_properties_when_persisted_edges_are_absent",
        },
    )


async def surface_entity_profile(session_factory, *, program_id: UUID, entity_key: str) -> WorkbenchEntityProfile | None:
    async with session_factory() as session:
        snapshot = await _latest_snapshot(session, program_id)
        if snapshot is None:
            return None
        if _is_surface_ui_group_key(entity_key):
            return await _surface_ui_group_profile(session, program_id, snapshot["id"], entity_key)
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
        if _is_surface_ui_group_key(entity_key):
            return WorkbenchActionAffordanceList(
                program_id=program_id,
                entity_key=entity_key,
                actions=[],
                boundary=workbench_read_boundary(surface="surface_ui_group_actions_read_only"),
            )
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
        if _is_surface_ui_group_key(entity_key):
            return await _surface_ui_group_memory(session, program_id, snapshot["id"], entity_key)
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


def _surface_overview_fetch_limit(limit: int, *, seeded: bool) -> int:
    if seeded:
        return max(1, min(limit, 1000))
    # The operator overview must not be filled by the first alphabetical node_type
    # bucket. Fetch a broader surface sample so hosts, route families, endpoints,
    # response shapes, and parameters can be grouped before the canvas applies its
    # own display cap.
    return max(limit, 2000)


def _surface_ui_grouping(node_rows: list[Mapping[str, Any]]) -> tuple[list[WorkbenchNode], list[WorkbenchEdge]]:
    hosts: dict[str, list[Mapping[str, Any]]] = {}
    families: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for row in node_rows:
        host = _text(row.get("host")) or "unknown-host"
        family = _path_family(row)
        hosts.setdefault(host, []).append(row)
        families.setdefault((host, family), []).append(row)

    nodes: list[WorkbenchNode] = []
    edges: list[WorkbenchEdge] = []
    for host, rows in sorted(hosts.items()):
        nodes.append(_ui_group_node(
            group_id=_ui_host_id(host),
            entity_key=_ui_host_key(host),
            node_type="host",
            label=host,
            caption=f"{len(rows)} surface nodes",
            badges=["host", "ui-group"],
            properties={"host": host, "derived_from": "surface_nodes"},
            metrics={"surface_node_count": len(rows)},
            rank=0,
        ))

    for (host, family), rows in sorted(families.items()):
        family_id = _ui_family_id(host, family)
        nodes.append(_ui_group_node(
            group_id=family_id,
            entity_key=_ui_family_key(host, family),
            node_type="route_family",
            label=family,
            caption=f"{host} · {len(rows)} nodes",
            badges=["route_family", "ui-group"],
            properties={"host": host, "route_family": family, "derived_from": "surface_nodes"},
            metrics={"surface_node_count": len(rows)},
            rank=1,
        ))
        edges.append(_ui_group_edge(_ui_host_id(host), family_id, "HAS_ROUTE_FAMILY", "route family"))
        for row in rows:
            edges.append(_ui_group_edge(family_id, _node_id(row["id"]), "CONTAINS_SURFACE_NODE", "contains"))
    return nodes, edges


def _ui_group_node(
    *,
    group_id: str,
    entity_key: str,
    node_type: str,
    label: str,
    caption: str,
    badges: list[str],
    properties: dict[str, Any],
    metrics: dict[str, Any],
    rank: int,
) -> WorkbenchNode:
    return WorkbenchNode(
        id=group_id,
        entity_key=entity_key,
        node_type=node_type,
        label=label,
        caption=caption,
        properties=properties,
        metadata={"derived": True, "ui_grouping": True},
        visual={"role": "group", "rank": rank},
        badges=badges,
        metrics=metrics,
        evidence_refs=[],
        action_affordance_count=0,
        staleness="fresh",
        confidence=0.8,
        source_refs=[{"type": "surface_ui_grouping", "id": entity_key}],
    )


def _ui_group_edge(source: str, target: str, relationship_type: str, label: str) -> WorkbenchEdge:
    return WorkbenchEdge(
        id=f"ui-edge:{source}:{target}",
        source=source,
        target=target,
        relationship_type=relationship_type,
        label=label,
        confidence=0.8,
        delta_state="unchanged",
        source_projection="surface_map_ui_grouping",
    )


def _path_family(row: Mapping[str, Any]) -> str:
    path = _text(row.get("route_template") or row.get("path")) or "/"
    clean = path if path.startswith("/") else f"/{path}"
    parts = [part for part in clean.strip("/").split("/") if part]
    if not parts:
        return "/"
    first = parts[0]
    return f"/{first}/*" if len(parts) > 1 else f"/{first}"


def _is_surface_ui_group_key(entity_key: str) -> bool:
    return entity_key.startswith("surface-ui:host:") or entity_key.startswith("surface-ui:family:")


def _ui_host_key(host: str) -> str:
    return f"surface-ui:host:{_pack_ui_value(host)}"


def _ui_family_key(host: str, family: str) -> str:
    return f"surface-ui:family:{_pack_ui_value(host)}:{_pack_ui_value(family)}"


def _ui_host_id(host: str) -> str:
    return f"ui:host:{_pack_ui_value(host)}"


def _ui_family_id(host: str, family: str) -> str:
    return f"ui:family:{_pack_ui_value(host)}:{_pack_ui_value(family)}"


def _pack_ui_value(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")


def _unpack_ui_value(value: str) -> str:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")


def _ui_group_parts(entity_key: str) -> tuple[str, str, str | None] | None:
    parts = entity_key.split(":")
    try:
        if len(parts) == 3 and parts[:2] == ["surface-ui", "host"]:
            host = _unpack_ui_value(parts[2])
            return ("host", host, None)
        if len(parts) == 4 and parts[:2] == ["surface-ui", "family"]:
            host = _unpack_ui_value(parts[2])
            family = _unpack_ui_value(parts[3])
            return ("family", host, family)
    except Exception:
        return None
    return None


async def _surface_ui_group_profile(
    session: Any,
    program_id: UUID,
    snapshot_id: UUID,
    entity_key: str,
) -> WorkbenchEntityProfile | None:
    rows = await _rows_for_ui_group(session, program_id, snapshot_id, entity_key, limit=1000)
    if rows is None:
        return None
    group = _ui_group_parts(entity_key)
    if group is None:
        return None
    group_type, host, family = group
    label = host if group_type == "host" else family or "route family"
    node_types = _value_counts(row.get("node_type") for row in rows)
    methods = _value_counts(row.get("method") for row in rows)
    statuses = _value_counts(row.get("status_code") for row in rows)
    examples = [_node_label(row, dict(row.get("features_json") or {})) for row in rows[:8]]
    return WorkbenchEntityProfile(
        program_id=program_id,
        entity_key=entity_key,
        profile={
            "label": label,
            "node_type": "surface_ui_group",
            "group_type": group_type,
            "host": host,
            "route_family": family,
            "snapshot_id": str(snapshot_id),
            "surface_node_count": len(rows),
            "node_types": node_types,
            "methods": methods,
            "status_codes": statuses,
            "examples": examples,
            "source_projection": "surface_map_ui_grouping",
        },
        properties={"host": host, "route_family": family, "derived_from": "surface_nodes"},
        evidence_refs=[{"type": "surface_node", "id": str(row["id"])} for row in rows[:20]],
        memory_pointers=[{"type": "surface_ui_grouping", "id": entity_key}],
        boundary=workbench_read_boundary(surface="surface_ui_group_profile"),
    )


async def _surface_ui_group_memory(
    session: Any,
    program_id: UUID,
    snapshot_id: UUID,
    entity_key: str,
) -> WorkbenchEntityMemory | None:
    rows = await _rows_for_ui_group(session, program_id, snapshot_id, entity_key, limit=1000)
    if rows is None:
        return None
    group = _ui_group_parts(entity_key)
    if group is None:
        return None
    _, host, family = group
    return WorkbenchEntityMemory(
        program_id=program_id,
        entity_key=entity_key,
        fragments=[
            {
                "id": f"surface-ui-fragment:{entity_key}",
                "kind": "surface_ui_group",
                "entity_key": entity_key,
                "host": host,
                "route_family": family,
                "surface_node_count": len(rows),
                "examples": [_node_label(row, dict(row.get("features_json") or {})) for row in rows[:10]],
            }
        ],
        tree_nodes=[
            {
                "id": f"surface-ui-tree:{entity_key}",
                "kind": "surface_ui_group",
                "label": family or host,
                "summary_is_truth": False,
            }
        ],
        summaries=[
            {
                "kind": "surface_ui_group_summary",
                "surface_node_count": len(rows),
                "summary_is_truth": False,
            }
        ],
        evidence_refs=[{"type": "surface_node", "id": str(row["id"])} for row in rows[:20]],
        boundary=workbench_read_boundary(surface="surface_ui_group_memory"),
    )


async def _rows_for_ui_group(
    session: Any,
    program_id: UUID,
    snapshot_id: UUID,
    entity_key: str,
    *,
    limit: int,
) -> list[Mapping[str, Any]] | None:
    group = _ui_group_parts(entity_key)
    if group is None:
        return None
    group_type, host, family = group
    rows = await _nodes_for_snapshot(session, program_id, snapshot_id, limit=limit)
    if group_type == "host":
        return [row for row in rows if (_text(row.get("host")) or "unknown-host") == host]
    return [
        row
        for row in rows
        if (_text(row.get("host")) or "unknown-host") == host and _path_family(row) == family
    ]


def _value_counts(values: object) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:  # type: ignore[assignment]
        text = _text(value)
        if text is None:
            continue
        counts[text] = counts.get(text, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:10])


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
    node_priority = case(
        (surface_nodes.c.node_type == "host", 0),
        (surface_nodes.c.node_type.in_(("service", "port")), 1),
        (surface_nodes.c.node_type.in_(("endpoint", "route_template")), 2),
        (surface_nodes.c.node_type == "param", 3),
        (surface_nodes.c.node_type == "response_shape", 4),
        else_=9,
    )
    statement = (
        select(*_NODE_COLUMNS)
        .where(surface_nodes.c.program_id == bindparam("program_id"))
        .where(surface_nodes.c.snapshot_id == bindparam("snapshot_id"))
        .order_by(node_priority.asc(), surface_nodes.c.host.asc(), surface_nodes.c.route_template.asc().nulls_last(), surface_nodes.c.path.asc().nulls_last())
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
