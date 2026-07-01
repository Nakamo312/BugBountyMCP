"""Neo4j/graph-projector read views for the Workbench.

This module exposes the existing graph-projector safe query templates to the
Workbench UI. It does not accept raw Cypher from the frontend, does not execute
GDS procedures, and does not mutate Neo4j. GDS output is still expected to be
materialized by graph-projector into PostgreSQL for component-analysis views;
these reads expose the ontology/projection graph that already exists in Neo4j.
"""
from __future__ import annotations

import asyncio
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, unquote
from uuid import UUID

from api.application.workbench import (
    WorkbenchActionAffordanceList,
    WorkbenchEdge,
    WorkbenchEntityMemory,
    WorkbenchEntityProfile,
    WorkbenchGraph,
    WorkbenchLens,
    WorkbenchNode,
)
from api.config import Settings

try:  # Imported from services/graph-projector, copied into the API image.
    from graph_projector.query_templates import default_query_template_registry
except ModuleNotFoundError:  # pragma: no cover - only happens in broken images.
    default_query_template_registry = None  # type: ignore[assignment]

_NEO4J_ENTITY_PREFIX = "neo4j:"
_SECRET_KEY_RE = re.compile(r"(token|secret|password|authorization|cookie|api[_-]?key|session)", re.IGNORECASE)
_SECRET_VALUE_RE = re.compile(
    r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+|((?:token|api[_-]?key|password|secret|session)\s*[=:]\s*)[^\s,;]+"
)

_TEMPLATE_BY_LENS: dict[WorkbenchLens, str] = {
    WorkbenchLens.NEO4J_EXPOSURE: "asset_exposure",
    WorkbenchLens.NEO4J_ENDPOINT: "endpoint_neighborhood",
    WorkbenchLens.NEO4J_EVIDENCE: "evidence_path",
    WorkbenchLens.NEO4J_SURFACE_MATH: "surface_graph_math",
    WorkbenchLens.NEO4J_ACTION_OUTCOME: "action_outcome_experience_neighborhood",
    WorkbenchLens.NEO4J_JS: "hidden_endpoints_from_js",
    WorkbenchLens.NEO4J_TECH: "exposed_services_by_technology",
    WorkbenchLens.NEO4J_HYPOTHESIS: "hypothesis_evidence_paths",
}

_LENS_LABELS: dict[WorkbenchLens, str] = {
    WorkbenchLens.NEO4J_EXPOSURE: "Neo4j · Exposure",
    WorkbenchLens.NEO4J_ENDPOINT: "Neo4j · Endpoint neighborhood",
    WorkbenchLens.NEO4J_EVIDENCE: "Neo4j · Evidence paths",
    WorkbenchLens.NEO4J_SURFACE_MATH: "Neo4j · Surface math",
    WorkbenchLens.NEO4J_ACTION_OUTCOME: "Neo4j · Action outcomes",
    WorkbenchLens.NEO4J_JS: "Neo4j · JS references",
    WorkbenchLens.NEO4J_TECH: "Neo4j · Services by technology",
    WorkbenchLens.NEO4J_HYPOTHESIS: "Neo4j · Hypothesis evidence",
}

_SEED_REQUIRED = {
    WorkbenchLens.NEO4J_ENDPOINT: "Select or focus an Endpoint node from any Neo4j view.",
    WorkbenchLens.NEO4J_EVIDENCE: "Select or focus a Neo4j entity to read its evidence path.",
}

_ENTITY_LABEL_PRIORITY = (
    "Program",
    "Scope",
    "Host",
    "IP",
    "ASN",
    "CIDR",
    "Service",
    "Endpoint",
    "Parameter",
    "JSFile",
    "Tool",
    "ToolRun",
    "ActionOutcome",
    "CapabilityProfile",
    "OutcomeFeature",
    "Artifact",
    "Observation",
    "Evidence",
    "SurfaceSnapshot",
    "SurfaceNode",
    "SurfaceFingerprint",
    "SurfaceDelta",
)

_NODE_TYPE_BY_LABEL = {
    "Program": "neo4j_program",
    "Scope": "neo4j_scope",
    "Host": "host",
    "IP": "neo4j_ip",
    "ASN": "neo4j_asn",
    "CIDR": "neo4j_cidr",
    "Service": "service",
    "Endpoint": "endpoint",
    "Parameter": "param",
    "JSFile": "neo4j_js_file",
    "Tool": "neo4j_tool",
    "ToolRun": "neo4j_tool_run",
    "ActionOutcome": "neo4j_action_outcome",
    "CapabilityProfile": "neo4j_capability_profile",
    "OutcomeFeature": "neo4j_outcome_feature",
    "Artifact": "artifact_ref",
    "Observation": "neo4j_observation",
    "Evidence": "neo4j_evidence",
    "SurfaceSnapshot": "neo4j_surface_snapshot",
    "SurfaceNode": "neo4j_surface_node",
    "SurfaceFingerprint": "neo4j_surface_fingerprint",
    "SurfaceDelta": "neo4j_surface_delta",
}

_LABEL_FIELDS = (
    "label",
    "name",
    "hostname",
    "host",
    "url",
    "normalized_path",
    "route_template",
    "path",
    "service_key",
    "technology",
    "capability_id",
    "profile_id",
    "tool_name",
    "outcome_id",
    "snapshot_id",
    "delta_type",
    "identity_key",
)

_CAPTION_FIELDS = (
    "scheme",
    "port",
    "method",
    "status_code",
    "content_type",
    "parser_version",
    "event_type",
    "source_type",
    "created_at",
    "last_seen",
)


@dataclass(frozen=True)
class Neo4jTemplateSpec:
    lens: WorkbenchLens
    template_name: str
    label: str


def neo4j_lenses() -> tuple[WorkbenchLens, ...]:
    return tuple(_TEMPLATE_BY_LENS)


def neo4j_lens_label(lens: WorkbenchLens) -> str:
    return _LENS_LABELS.get(lens, lens.value)


def is_neo4j_lens(lens: WorkbenchLens) -> bool:
    return lens in _TEMPLATE_BY_LENS


def is_neo4j_entity_key(entity_key: str) -> bool:
    return entity_key.startswith(_NEO4J_ENTITY_PREFIX)


async def build_neo4j_lens_graph(
    *,
    settings: Settings,
    program_id: UUID,
    lens: WorkbenchLens,
    seed: str | None = None,
    depth: int = 1,
    limit: int = 250,
) -> WorkbenchGraph:
    if lens not in _TEMPLATE_BY_LENS:
        return _message_graph(
            program_id=program_id,
            lens=lens,
            seed=seed,
            message=f"Unsupported Neo4j workbench lens: {lens.value}",
            reason="unsupported_neo4j_lens",
        )
    if default_query_template_registry is None:
        return _message_graph(
            program_id=program_id,
            lens=lens,
            seed=seed,
            message="graph-projector query template registry is not importable in the API image.",
            reason="graph_projector_templates_unavailable",
        )

    template_name = _TEMPLATE_BY_LENS[lens]
    required_seed_reason = _SEED_REQUIRED.get(lens)
    identity_key = _identity_key_from_seed(seed)
    if required_seed_reason and not identity_key:
        return _message_graph(
            program_id=program_id,
            lens=lens,
            seed=seed,
            message=required_seed_reason,
            reason="seed_required_for_template",
            template_name=template_name,
        )

    safe_limit = _workbench_query_limit(settings, limit)
    parameters: dict[str, object] = {"program_id": str(program_id), "limit": safe_limit}
    if lens in {WorkbenchLens.NEO4J_ENDPOINT, WorkbenchLens.NEO4J_EVIDENCE}:
        parameters["identity_key"] = identity_key or ""
    elif lens == WorkbenchLens.NEO4J_SURFACE_MATH:
        snapshot_id = _snapshot_id_from_seed(seed)
        if not snapshot_id:
            return _message_graph(
                program_id=program_id,
                lens=lens,
                seed=seed,
                message="Focus a SurfaceSnapshot node or open Surface Components to select the snapshot-local graph math view.",
                reason="snapshot_seed_required_for_surface_graph_math",
                template_name=template_name,
            )
        parameters["snapshot_id"] = snapshot_id
    elif lens == WorkbenchLens.NEO4J_ACTION_OUTCOME:
        parameters["outcome_id"] = _outcome_id_from_seed(seed)
    elif lens == WorkbenchLens.NEO4J_TECH:
        parameters["technology"] = _technology_from_seed(seed)
    elif lens == WorkbenchLens.NEO4J_HYPOTHESIS:
        parameters["hypothesis_id"] = _hypothesis_id_from_seed(seed)

    try:
        registry = default_query_template_registry()
        rendered = registry.get(template_name).render(parameters)
        rows = await _execute_neo4j_read(settings, rendered.cypher, dict(rendered.parameters))
    except Exception as exc:  # noqa: BLE001 - backend must degrade to a visible graph state.
        return _message_graph(
            program_id=program_id,
            lens=lens,
            seed=seed,
            message=f"Neo4j read failed: {_redact_text(str(exc))}",
            reason="neo4j_read_failed",
            template_name=template_name,
        )

    nodes, edges = _graph_from_records(rows)
    if not nodes:
        return _message_graph(
            program_id=program_id,
            lens=lens,
            seed=seed,
            message=f"Neo4j template {template_name} returned no graph rows for this program/seed.",
            reason="neo4j_template_empty_result",
            template_name=template_name,
        )
    return WorkbenchGraph(
        program_id=program_id,
        lens=lens,
        seed=seed,
        depth=depth,
        nodes=list(nodes.values())[:safe_limit],
        edges=list(edges.values())[: max(1, min(safe_limit * 4, 2000))],
        counts={
            "nodes": len(nodes),
            "edges": len(edges),
            "neo4j_rows": len(rows),
        },
        boundary=_neo4j_boundary(surface=f"neo4j_template_{template_name}", template_name=template_name),
    )


async def neo4j_entity_profile(
    *,
    settings: Settings,
    program_id: UUID,
    entity_key: str,
) -> WorkbenchEntityProfile | None:
    identity_key = _identity_key_from_seed(entity_key)
    if not identity_key:
        return None
    cypher = """
MATCH (entity {program_id: $program_id, identity_key: $identity_key})
RETURN entity
LIMIT 1
""".strip()
    try:
        rows = await _execute_neo4j_read(settings, cypher, {"program_id": str(program_id), "identity_key": identity_key})
    except Exception as exc:  # noqa: BLE001
        return WorkbenchEntityProfile(
            program_id=program_id,
            entity_key=entity_key,
            profile={"error": _redact_text(str(exc)), "source": "neo4j_read_failed"},
            boundary=_neo4j_boundary(surface="neo4j_entity_profile", template_name="entity_profile"),
        )
    nodes, _edges = _graph_from_records(rows)
    node = next(iter(nodes.values()), None)
    if node is None:
        return None
    return WorkbenchEntityProfile(
        program_id=program_id,
        entity_key=entity_key,
        profile={
            "type": node.node_type,
            "label": node.label,
            "caption": node.caption,
            "projection_source": "neo4j_graph_projector_ontology",
            "identity_key": identity_key,
            "labels": node.metadata.get("labels", []),
            "safe_query_templates": list(_TEMPLATE_BY_LENS.values()),
        },
        properties=node.properties,
        evidence_refs=node.evidence_refs,
        boundary=_neo4j_boundary(surface="neo4j_entity_profile", template_name="entity_profile"),
    )


def neo4j_entity_actions(*, program_id: UUID, entity_key: str) -> WorkbenchActionAffordanceList:
    return WorkbenchActionAffordanceList(
        program_id=program_id,
        entity_key=entity_key,
        actions=[],
        boundary={
            **_neo4j_boundary(surface="neo4j_read_only_no_action_affordances", template_name="entity_actions"),
            "reason": "Neo4j workbench views are read-only. Actions must go through ActionService/catalog/policy.",
        },
    )


def neo4j_entity_memory(*, program_id: UUID, entity_key: str) -> WorkbenchEntityMemory:
    return WorkbenchEntityMemory(
        program_id=program_id,
        entity_key=entity_key,
        fragments=[
            {
                "kind": "neo4j_entity_pointer",
                "entity_key": entity_key,
                "summary": "Use Neo4j evidence/action-outcome lenses to inspect lineage and prior action memory.",
            }
        ],
        boundary=_neo4j_boundary(surface="neo4j_entity_memory_pointer", template_name="entity_memory"),
    )


async def _execute_neo4j_read(settings: Settings, cypher: str, parameters: dict[str, object]) -> list[dict[str, Any]]:
    try:
        from neo4j import GraphDatabase, Query
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise RuntimeError("neo4j package is not installed in the API image") from exc

    def run() -> list[dict[str, Any]]:
        driver = GraphDatabase.driver(settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD), max_transaction_retry_time=_workbench_read_timeout(settings))
        try:
            with driver.session(database=settings.NEO4J_DATABASE, default_access_mode="READ") as session:
                result = session.run(Query(cypher, timeout=_workbench_read_timeout(settings)), parameters)
                return [dict(record) for record in result]
        finally:
            driver.close()

    return await asyncio.to_thread(run)



def _workbench_read_timeout(settings: Settings) -> float:
    try:
        configured = float(settings.NEO4J_WORKBENCH_READ_TIMEOUT_SECONDS)
    except (TypeError, ValueError):
        configured = 20.0
    return max(5.0, min(configured, 120.0))


def _workbench_query_limit(settings: Settings, requested: int) -> int:
    try:
        configured_max = int(settings.NEO4J_WORKBENCH_MAX_LIMIT)
    except (TypeError, ValueError):
        configured_max = 200
    bounded_max = max(25, min(configured_max, 500))
    return max(1, min(int(requested or bounded_max), bounded_max))

def _graph_from_records(records: Iterable[Mapping[str, Any]]) -> tuple[dict[str, WorkbenchNode], dict[str, WorkbenchEdge]]:
    nodes: dict[str, WorkbenchNode] = {}
    edges: dict[str, WorkbenchEdge] = {}
    for record in records:
        _collect_graph_values(record.values(), nodes=nodes, edges=edges)
    return nodes, edges


def _collect_graph_values(values: Iterable[Any], *, nodes: dict[str, WorkbenchNode], edges: dict[str, WorkbenchEdge]) -> None:
    for value in values:
        if _is_neo4j_path(value):
            path_nodes = list(value.nodes)
            path_relationships = list(value.relationships)
            for node in path_nodes:
                _add_node(node, nodes)
            for relationship in path_relationships:
                _add_relationship(relationship, edges)
        elif _is_neo4j_node(value):
            _add_node(value, nodes)
        elif _is_neo4j_relationship(value):
            _add_relationship(value, edges)
        elif isinstance(value, Mapping):
            _collect_graph_values(value.values(), nodes=nodes, edges=edges)
        elif isinstance(value, (list, tuple, set)):
            _collect_graph_values(value, nodes=nodes, edges=edges)


def _add_node(raw_node: Any, nodes: dict[str, WorkbenchNode]) -> None:
    node_id = _neo4j_element_id(raw_node)
    if not node_id or node_id in nodes:
        return
    labels = _node_labels(raw_node)
    properties = _safe_mapping(dict(raw_node.items()) if hasattr(raw_node, "items") else {})
    primary_label = _primary_label(labels)
    identity = str(properties.get("identity_key") or properties.get("snapshot_id") or properties.get("outcome_id") or node_id)
    entity_key = f"neo4j:{quote(primary_label, safe='')}:{quote(identity, safe='')}"
    node_type = _NODE_TYPE_BY_LABEL.get(primary_label, f"neo4j_{_snake(primary_label)}")
    label = _best_label(properties, labels, node_id)
    nodes[node_id] = WorkbenchNode(
        id=node_id,
        entity_key=entity_key,
        node_type=node_type,
        label=label,
        caption=_best_caption(properties),
        properties=properties,
        metadata={
            "labels": labels,
            "projection_source": "neo4j_graph_projector_ontology",
            "identity_key": identity,
            "raw_neo4j_shape": "redacted_properties_only",
        },
        badges=["Neo4j", primary_label],
        metrics=_node_metrics(properties),
        evidence_refs=_evidence_refs_from_properties(properties),
        staleness="unknown",
        confidence=0.8,
        source_refs=[{"type": "neo4j", "label": primary_label, "identity_key": identity}],
    )


def _add_relationship(raw_relationship: Any, edges: dict[str, WorkbenchEdge]) -> None:
    edge_id = _neo4j_element_id(raw_relationship)
    if not edge_id or edge_id in edges:
        return
    source = _relationship_node_id(raw_relationship, "start_node") or _relationship_node_id(raw_relationship, "start_node_id")
    target = _relationship_node_id(raw_relationship, "end_node") or _relationship_node_id(raw_relationship, "end_node_id")
    if not source or not target:
        return
    rel_type = str(getattr(raw_relationship, "type", None) or getattr(raw_relationship, "__class__", type(raw_relationship)).__name__)
    properties = _safe_mapping(dict(raw_relationship.items()) if hasattr(raw_relationship, "items") else {})
    edges[edge_id] = WorkbenchEdge(
        id=edge_id,
        source=source,
        target=target,
        relationship_type=rel_type,
        label=_humanize(rel_type),
        caption=_best_caption(properties),
        weight=float(properties.get("weight") or 1.0),
        confidence=0.9,
        evidence_refs=_evidence_refs_from_properties(properties),
        source_projection="neo4j_graph_projector_template",
    )


def _relationship_node_id(raw_relationship: Any, attr: str) -> str | None:
    value = getattr(raw_relationship, attr, None)
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return str(value)
    return _neo4j_element_id(value)


def _is_neo4j_node(value: Any) -> bool:
    return hasattr(value, "labels") and hasattr(value, "items") and not hasattr(value, "type")


def _is_neo4j_relationship(value: Any) -> bool:
    return hasattr(value, "type") and hasattr(value, "items") and (
        hasattr(value, "start_node") or hasattr(value, "start_node_id")
    )


def _is_neo4j_path(value: Any) -> bool:
    return hasattr(value, "nodes") and hasattr(value, "relationships")


def _neo4j_element_id(value: Any) -> str | None:
    element_id = getattr(value, "element_id", None)
    if element_id:
        return f"neo4j:{element_id}"
    numeric_id = getattr(value, "id", None)
    if numeric_id is not None:
        return f"neo4j:{numeric_id}"
    return None


def _node_labels(raw_node: Any) -> list[str]:
    try:
        return sorted(str(label) for label in raw_node.labels)
    except Exception:  # noqa: BLE001
        return []


def _primary_label(labels: list[str]) -> str:
    for label in _ENTITY_LABEL_PRIORITY:
        if label in labels:
            return label
    return labels[0] if labels else "Node"


def _best_label(properties: Mapping[str, Any], labels: list[str], fallback: str) -> str:
    method = properties.get("method")
    path = properties.get("route_template") or properties.get("normalized_path") or properties.get("path")
    if method and path:
        return f"{method} {path}"
    if properties.get("scheme") and properties.get("port"):
        return f"{properties.get('scheme')}:{properties.get('port')}"
    for field in _LABEL_FIELDS:
        value = properties.get(field)
        if value not in (None, "", []):
            return str(value)
    return _primary_label(labels) or fallback


def _best_caption(properties: Mapping[str, Any]) -> str | None:
    parts = []
    for field in _CAPTION_FIELDS:
        value = properties.get(field)
        if value not in (None, "", []):
            parts.append(str(value))
    return ", ".join(parts[:4]) or None


def _node_metrics(properties: Mapping[str, Any]) -> dict[str, Any]:
    metrics = {}
    for key in (
        "degree",
        "betweenness",
        "score",
        "utility_score",
        "confidence",
        "status_code",
        "port",
        "node_count",
        "changed_node_count",
    ):
        if key in properties:
            metrics[key] = properties[key]
    return metrics


def _evidence_refs_from_properties(properties: Mapping[str, Any]) -> list[dict[str, Any]]:
    refs = []
    for key in ("ref_id", "artifact_id", "observation_id", "evidence_id", "run_id", "outcome_id"):
        if properties.get(key):
            refs.append({"type": key.removesuffix("_id"), "id": str(properties[key])})
    return refs[:6]


def _safe_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): _safe_value(str(key), raw_value) for key, raw_value in value.items() if _safe_value(str(key), raw_value) is not None}


def _safe_value(key: str, value: Any) -> Any:
    if _SECRET_KEY_RE.search(key):
        return "[REDACTED]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _redact_text(value[:2048])
    if isinstance(value, (list, tuple, set)):
        return [_safe_value(key, item) for item in list(value)[:25]]
    if isinstance(value, Mapping):
        return _safe_mapping(value)
    return _redact_text(str(value)[:2048])


def _redact_text(value: str) -> str:
    return _SECRET_VALUE_RE.sub(lambda match: f"{match.group(1) or match.group(2)}[REDACTED]", value)


def _humanize(value: str) -> str:
    return value.lower().replace("_", " ")


def _snake(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "node"


def _identity_key_from_seed(seed: str | None) -> str | None:
    if not seed:
        return None
    if seed.startswith(_NEO4J_ENTITY_PREFIX):
        parts = seed.split(":", 2)
        if len(parts) == 3:
            return unquote(parts[2])
    return seed


def _snapshot_id_from_seed(seed: str | None) -> str | None:
    identity = _identity_key_from_seed(seed)
    if not identity:
        return None
    if len(identity) >= 32:
        return identity
    return None


def _outcome_id_from_seed(seed: str | None) -> str | None:
    return _identity_key_from_seed(seed)


def _technology_from_seed(seed: str | None) -> str | None:
    identity = _identity_key_from_seed(seed)
    if not identity or identity.startswith("surface") or identity.startswith("neo4j"):
        return None
    return identity


def _hypothesis_id_from_seed(seed: str | None) -> str | None:
    return _identity_key_from_seed(seed)


def _message_graph(
    *,
    program_id: UUID,
    lens: WorkbenchLens,
    seed: str | None,
    message: str,
    reason: str,
    template_name: str | None = None,
) -> WorkbenchGraph:
    boundary = _neo4j_boundary(surface=f"neo4j_{reason}", template_name=template_name or "none")
    boundary.update(
        {
            "status": "unavailable",
            "reason": reason,
            "message": message,
            "ui_empty_state": True,
            "render_as_graph_node": False,
        }
    )
    return WorkbenchGraph(
        program_id=program_id,
        lens=lens,
        seed=seed,
        nodes=[],
        edges=[],
        counts={"nodes": 0, "edges": 0},
        boundary=boundary,
    )


def _neo4j_boundary(*, surface: str, template_name: str) -> dict[str, Any]:
    return {
        "surface": surface,
        "postgres_write": "forbidden",
        "neo4j_read": "allowlisted_graph_projector_templates_only",
        "neo4j_write": "forbidden",
        "raw_cypher": "forbidden",
        "template": template_name,
        "template_registry": "graph_projector.query_templates.default_query_template_registry",
        "gds_execution": "forbidden_in_workbench_request_path",
        "gds_source": "read_existing_neo4j_projection_or_materialized_graph_projector_results",
        "proposal_creation": "forbidden",
        "action_submission": "forbidden",
        "tool_execution": "forbidden",
        "raw_secret_material": "forbidden",
    }
