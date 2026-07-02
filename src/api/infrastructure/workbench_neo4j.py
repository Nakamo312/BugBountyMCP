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
    WorkbenchLens.NEO4J_EXPOSURE: "Exposure map",
    WorkbenchLens.NEO4J_ENDPOINT: "Endpoint map",
    WorkbenchLens.NEO4J_EVIDENCE: "Evidence paths",
    WorkbenchLens.NEO4J_SURFACE_MATH: "Graph signals",
    WorkbenchLens.NEO4J_ACTION_OUTCOME: "Outcomes",
    WorkbenchLens.NEO4J_JS: "JS references",
    WorkbenchLens.NEO4J_TECH: "Services",
    WorkbenchLens.NEO4J_HYPOTHESIS: "Hypothesis evidence",
}

# These lenses read the existing graph materialization as-is. They must not
# synthesize PostgreSQL fallback nodes or require the operator to understand
# Neo4j/template internals. Seed values narrow the graph when available; they
# are not required for the default overview.

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

_LABEL_VISUALS: dict[str, dict[str, Any]] = {
    "Program": {"lane": "Program", "tier": 0, "priority": 100, "radius": 9, "color": "#111827", "label_policy": "always", "overview_limit": 8},
    "Scope": {"lane": "Scope", "tier": 0, "priority": 92, "radius": 7, "color": "#475569", "label_policy": "always", "overview_limit": 12},
    "ASN": {"lane": "Network", "tier": 1, "priority": 94, "radius": 7, "color": "#0f766e", "label_policy": "always", "overview_limit": 30},
    "CIDR": {"lane": "Network", "tier": 2, "priority": 92, "radius": 7, "color": "#0e7490", "label_policy": "always", "overview_limit": 60},
    "IP": {"lane": "Network", "tier": 3, "priority": 86, "radius": 6, "color": "#0369a1", "label_policy": "important", "overview_limit": 90},
    "Host": {"lane": "Assets", "tier": 4, "priority": 84, "radius": 6.5, "color": "#0f172a", "label_policy": "important", "overview_limit": 110},
    "Service": {"lane": "Services", "tier": 5, "priority": 80, "radius": 5.5, "color": "#334155", "label_policy": "important", "overview_limit": 100},
    "Endpoint": {"lane": "HTTP", "tier": 6, "priority": 54, "radius": 3.6, "color": "#059669", "label_policy": "hover", "overview_limit": 70},
    "Parameter": {"lane": "Inputs", "tier": 7, "priority": 42, "radius": 3.2, "color": "#d97706", "label_policy": "hover", "overview_limit": 40},
    "JSFile": {"lane": "Client JS", "tier": 5, "priority": 72, "radius": 4.8, "color": "#ca8a04", "label_policy": "important", "overview_limit": 70},
    "Evidence": {"lane": "Evidence", "tier": 8, "priority": 64, "radius": 4.2, "color": "#0f766e", "label_policy": "hover", "overview_limit": 50},
    "Observation": {"lane": "Evidence", "tier": 8, "priority": 58, "radius": 3.8, "color": "#0891b2", "label_policy": "hover", "overview_limit": 50},
    "Artifact": {"lane": "Evidence", "tier": 8, "priority": 50, "radius": 3.4, "color": "#475569", "label_policy": "hover", "overview_limit": 40},
    "ActionOutcome": {"lane": "Outcomes", "tier": 8, "priority": 76, "radius": 5.2, "color": "#ea580c", "label_policy": "important", "overview_limit": 60},
    "ToolRun": {"lane": "Outcomes", "tier": 7, "priority": 68, "radius": 4.5, "color": "#92400e", "label_policy": "hover", "overview_limit": 60},
    "Tool": {"lane": "Outcomes", "tier": 6, "priority": 60, "radius": 4.2, "color": "#78716c", "label_policy": "hover", "overview_limit": 40},
    "CapabilityProfile": {"lane": "Outcomes", "tier": 6, "priority": 60, "radius": 4.2, "color": "#7c3aed", "label_policy": "hover", "overview_limit": 40},
    "OutcomeFeature": {"lane": "Outcomes", "tier": 9, "priority": 44, "radius": 3.6, "color": "#9333ea", "label_policy": "hover", "overview_limit": 40},
    "SurfaceSnapshot": {"lane": "Surface", "tier": 1, "priority": 86, "radius": 6, "color": "#1d4ed8", "label_policy": "always", "overview_limit": 10},
    "SurfaceNode": {"lane": "Surface", "tier": 2, "priority": 46, "radius": 3.8, "color": "#2563eb", "label_policy": "hover", "overview_limit": 80},
    "SurfaceFingerprint": {"lane": "Surface", "tier": 3, "priority": 42, "radius": 3.5, "color": "#64748b", "label_policy": "hover", "overview_limit": 60},
    "SurfaceDelta": {"lane": "Surface", "tier": 4, "priority": 60, "radius": 4.2, "color": "#be123c", "label_policy": "important", "overview_limit": 60},
}

_LENS_LAYOUTS: dict[WorkbenchLens, dict[str, Any]] = {
    WorkbenchLens.NEO4J_EXPOSURE: {"title": "Exposure map", "lanes": ["Scope", "Network", "Assets", "Services", "HTTP", "Inputs"]},
    WorkbenchLens.NEO4J_ENDPOINT: {"title": "Endpoint map", "lanes": ["Assets", "Services", "HTTP", "Inputs", "Client JS", "Evidence"]},
    WorkbenchLens.NEO4J_EVIDENCE: {"title": "Evidence paths", "lanes": ["Assets", "Services", "HTTP", "Evidence"]},
    WorkbenchLens.NEO4J_SURFACE_MATH: {"title": "Graph signals", "lanes": ["Surface"]},
    WorkbenchLens.NEO4J_ACTION_OUTCOME: {"title": "Outcomes", "lanes": ["Assets", "Services", "HTTP", "Outcomes"]},
    WorkbenchLens.NEO4J_JS: {"title": "JS references", "lanes": ["Assets", "Services", "HTTP", "Inputs", "Client JS"]},
    WorkbenchLens.NEO4J_TECH: {"title": "Services", "lanes": ["Network", "Assets", "Services", "HTTP", "Inputs"]},
    WorkbenchLens.NEO4J_HYPOTHESIS: {"title": "Hypothesis evidence", "lanes": ["Assets", "Services", "HTTP", "Evidence"]},
}

_NATIVE_LABELS_BY_LENS: dict[WorkbenchLens, tuple[str, ...]] = {
    WorkbenchLens.NEO4J_EXPOSURE: ("ASN", "CIDR", "IP", "Host", "Scope", "Service", "Endpoint", "Parameter"),
    WorkbenchLens.NEO4J_ENDPOINT: ("Endpoint", "Parameter", "Service", "Host", "IP", "JSFile", "Observation", "Artifact"),
    WorkbenchLens.NEO4J_EVIDENCE: ("Evidence", "Observation", "Artifact", "Endpoint", "Service", "Host", "IP"),
    WorkbenchLens.NEO4J_SURFACE_MATH: ("SurfaceSnapshot", "SurfaceNode", "SurfaceFingerprint", "SurfaceDelta", "SurfaceComponentProbe"),
    WorkbenchLens.NEO4J_ACTION_OUTCOME: ("ActionOutcome", "ToolRun", "Tool", "CapabilityProfile", "OutcomeFeature", "Endpoint", "Service", "Host"),
    WorkbenchLens.NEO4J_JS: ("JSFile", "Endpoint", "Parameter", "Service", "Host", "Observation", "Artifact"),
    WorkbenchLens.NEO4J_TECH: ("Service", "Endpoint", "Parameter", "Host", "IP"),
    WorkbenchLens.NEO4J_HYPOTHESIS: ("Hypothesis", "HypothesisCandidate", "Evidence", "Observation", "Artifact", "Endpoint", "Service", "Host"),
}

_NATIVE_RELATIONSHIPS_BY_LENS: dict[WorkbenchLens, tuple[str, ...]] = {
    WorkbenchLens.NEO4J_EXPOSURE: ("HAS_SCOPE", "MATCHES_SCOPE", "RESOLVES_TO", "IN_CIDR", "ANNOUNCED_BY", "EXPOSES_SERVICE", "HAS_ENDPOINT", "HAS_PARAM"),
    WorkbenchLens.NEO4J_ENDPOINT: ("RESOLVES_TO", "EXPOSES_SERVICE", "HAS_ENDPOINT", "HAS_PARAM", "REFERENCES", "PRODUCED_OBSERVATION", "DESCRIBES"),
    WorkbenchLens.NEO4J_EVIDENCE: ("PRODUCED_ARTIFACT", "PRODUCED_OBSERVATION", "DESCRIBES", "SUPPORTS_EVIDENCE", "DERIVED_FROM"),
    WorkbenchLens.NEO4J_SURFACE_MATH: ("HAS_SURFACE_NODE", "HAS_SURFACE_FINGERPRINT", "SURFACE_EDGE", "HAS_SURFACE_DELTA", "HAS_SURFACE_FINGERPRINT_FEATURE"),
    WorkbenchLens.NEO4J_ACTION_OUTCOME: ("HAS_TOOL_RUN", "HAS_ACTION_OUTCOME", "OUTCOME_OF_RUN", "USED_CAPABILITY_PROFILE", "HAS_OUTCOME_FEATURE", "BEFORE_SURFACE_SNAPSHOT", "AFTER_SURFACE_SNAPSHOT", "USED_TOOL"),
    WorkbenchLens.NEO4J_JS: ("REFERENCES", "HAS_ENDPOINT", "HAS_PARAM", "DESCRIBES", "PRODUCED_OBSERVATION"),
    WorkbenchLens.NEO4J_TECH: ("EXPOSES_SERVICE", "HAS_ENDPOINT", "HAS_PARAM", "DESCRIBES"),
    WorkbenchLens.NEO4J_HYPOTHESIS: ("SUPPORTS_EVIDENCE", "DERIVED_FROM", "DESCRIBES"),
}


@dataclass(frozen=True)
class Neo4jSchemaState:
    labels: frozenset[str]
    relationships: frozenset[str]
    properties: frozenset[str]

    def has_any_graph_content(self) -> bool:
        return bool(self.labels or self.relationships or self.properties)

    def labels_for_lens(self, lens: WorkbenchLens) -> tuple[str, ...]:
        return tuple(label for label in _NATIVE_LABELS_BY_LENS.get(lens, ()) if label in self.labels)

    def relationships_for_lens(self, lens: WorkbenchLens) -> tuple[str, ...]:
        return tuple(rel for rel in _NATIVE_RELATIONSHIPS_BY_LENS.get(lens, ()) if rel in self.relationships)


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
            message=f"Unsupported relationship graph view: {lens.value}",
            reason="unsupported_relationship_lens",
        )

    schema_state = await _neo4j_schema_state(settings)
    template_name = _TEMPLATE_BY_LENS[lens]
    if "program_id" not in schema_state.properties:
        return _message_graph(
            program_id=program_id,
            lens=lens,
            seed=seed,
            message="Relationship graph has not been built for this database yet.",
            reason="relationship_graph_not_built",
            template_name=template_name,
            status="not_built",
            details={
                "available_labels": sorted(schema_state.labels),
                "available_relationships": sorted(schema_state.relationships),
            },
        )

    graph = await _build_native_neo4j_lens_graph(
        settings=settings,
        program_id=program_id,
        lens=lens,
        seed=seed,
        depth=depth,
        limit=limit,
        schema_state=schema_state,
        template_name=template_name,
    )
    if graph.nodes or (graph.boundary or {}).get("reason") != "relationship_graph_view_not_represented":
        return graph

    # The native graph reader is the default because it displays the ontology as
    # stored in Neo4j. Keep the allowlisted template path only as a compatibility
    # fallback for older graph-projector images that materialize a narrower shape.
    if default_query_template_registry is None:
        return graph
    try:
        safe_limit = _workbench_query_limit(settings, limit)
        parameters: dict[str, object] = {"program_id": str(program_id), "limit": safe_limit}
        identity_key = _identity_key_from_seed(seed)
        if lens in {WorkbenchLens.NEO4J_ENDPOINT, WorkbenchLens.NEO4J_EVIDENCE}:
            parameters["identity_key"] = identity_key or ""
        elif lens == WorkbenchLens.NEO4J_SURFACE_MATH:
            snapshot_id = _snapshot_id_from_seed(seed)
            if snapshot_id:
                parameters["snapshot_id"] = snapshot_id
        elif lens == WorkbenchLens.NEO4J_ACTION_OUTCOME:
            parameters["outcome_id"] = _outcome_id_from_seed(seed)
        elif lens == WorkbenchLens.NEO4J_TECH:
            parameters["technology"] = _technology_from_seed(seed)
        elif lens == WorkbenchLens.NEO4J_HYPOTHESIS:
            parameters["hypothesis_id"] = _hypothesis_id_from_seed(seed)
        registry = default_query_template_registry()
        rendered = registry.get(template_name).render(parameters)
        rows = await _execute_neo4j_read(settings, rendered.cypher, dict(rendered.parameters))
    except Exception as exc:  # noqa: BLE001 - backend must degrade to a visible graph state.
        return _message_graph(
            program_id=program_id,
            lens=lens,
            seed=seed,
            message=f"Relationship graph read failed: {_redact_text(str(exc))}",
            reason="relationship_graph_read_failed",
            template_name=template_name,
        )

    nodes, edges = _graph_from_records(rows)
    if not nodes:
        return graph
    return WorkbenchGraph(
        program_id=program_id,
        lens=lens,
        seed=seed,
        depth=depth,
        nodes=list(nodes.values())[:safe_limit],
        edges=list(edges.values())[: max(1, min(safe_limit * 4, 2000))],
        counts={"nodes": len(nodes), "edges": len(edges), "template_rows": len(rows)},
        boundary=_neo4j_boundary(surface=f"relationship_template_{template_name}", template_name=template_name),
    )


async def _build_native_neo4j_lens_graph(
    *,
    settings: Settings,
    program_id: UUID,
    lens: WorkbenchLens,
    seed: str | None,
    depth: int,
    limit: int,
    schema_state: Neo4jSchemaState,
    template_name: str,
) -> WorkbenchGraph:
    labels = schema_state.labels_for_lens(lens)
    relationships = schema_state.relationships_for_lens(lens)
    if not labels:
        return _message_graph(
            program_id=program_id,
            lens=lens,
            seed=seed,
            message="This graph view is not represented in the current relationship graph yet.",
            reason="relationship_graph_view_not_represented",
            template_name=template_name,
            status="empty",
            details={
                "available_labels": sorted(schema_state.labels),
                "available_relationships": sorted(schema_state.relationships),
            },
        )

    safe_limit = _workbench_query_limit(settings, limit)
    safe_depth = max(1, min(int(depth or 1), 3))
    identity_key = _identity_key_from_seed(seed)
    per_label_limit = max(8, min(90, safe_limit // max(1, len(labels))))
    parameters: dict[str, object] = {
        "program_id": str(program_id),
        "labels": list(labels),
        "relationships": list(relationships),
        "limit": safe_limit,
        "per_label_limit": per_label_limit,
        "path_limit": max(1, min(safe_limit * 4, 2000)),
    }
    if identity_key and _seed_predicate(schema_state):
        parameters["identity_key"] = identity_key
        cypher = _native_seed_cypher(schema_state=schema_state, relationships=relationships, depth=safe_depth)
    else:
        cypher = _native_overview_cypher(schema_state=schema_state, relationships=relationships, depth=safe_depth)

    try:
        rows = await _execute_neo4j_read(settings, cypher, parameters)
    except Exception as exc:  # noqa: BLE001
        return _message_graph(
            program_id=program_id,
            lens=lens,
            seed=seed,
            message=f"Relationship graph read failed: {_redact_text(str(exc))}",
            reason="relationship_graph_read_failed",
            template_name=template_name,
            details={"view": lens.value},
        )

    nodes, edges = _graph_from_records(rows)
    if not nodes:
        return _message_graph(
            program_id=program_id,
            lens=lens,
            seed=seed,
            message="No matching nodes are present in this relationship graph view.",
            reason="relationship_graph_view_empty",
            template_name=template_name,
            status="empty",
            details={
                "labels_used": list(labels),
                "relationships_used": list(relationships),
                "seed": seed,
            },
        )

    visible_nodes = list(nodes.values())[:safe_limit]
    node_ids = {node.id for node in visible_nodes}
    visible_edges = [edge for edge in edges.values() if edge.source in node_ids and edge.target in node_ids]
    return WorkbenchGraph(
        program_id=program_id,
        lens=lens,
        seed=seed,
        depth=safe_depth,
        nodes=visible_nodes,
        edges=visible_edges[: max(1, min(safe_limit * 4, 2000))],
        counts={
            "nodes": len(visible_nodes),
            "edges": len(visible_edges),
            "neo4j_nodes_seen": len(nodes),
            "neo4j_edges_seen": len(edges),
            **_label_counts(visible_nodes),
        },
        boundary={
            **_neo4j_boundary(surface="relationship_graph_native_read", template_name=template_name),
            "status": "ready",
            "view_labels": list(labels),
            "view_relationships": list(relationships),
            "operator_projection": "existing_neo4j_relationship_graph",
            "layout": _lens_layout(lens),
            "label_counts": _label_count_map(visible_nodes),
        },
    )


def _native_overview_cypher(*, schema_state: Neo4jSchemaState, relationships: tuple[str, ...], depth: int) -> str:
    order_expr = _node_order_expression("n", schema_state)
    if not relationships:
        return f"""
MATCH (n)
WHERE n.program_id = $program_id
  AND any(label IN labels(n) WHERE label IN $labels)
WITH n, [label IN $labels WHERE label IN labels(n)][0] AS lens_label
ORDER BY lens_label, {order_expr}
WITH lens_label, collect(n)[0..$per_label_limit] AS label_nodes
WITH reduce(selected = [], group IN collect(label_nodes) | selected + group)[0..$limit] AS selected_nodes
RETURN selected_nodes AS nodes, [] AS paths
""".strip()
    return f"""
MATCH (n)
WHERE n.program_id = $program_id
  AND any(label IN labels(n) WHERE label IN $labels)
WITH n, [label IN $labels WHERE label IN labels(n)][0] AS lens_label
ORDER BY lens_label, {order_expr}
WITH lens_label, collect(n)[0..$per_label_limit] AS label_nodes
WITH reduce(selected = [], group IN collect(label_nodes) | selected + group)[0..$limit] AS selected_nodes
UNWIND selected_nodes AS n
OPTIONAL MATCH path = (n)-[*1..{depth}]-(neighbor)
WHERE all(node IN nodes(path) WHERE node.program_id = $program_id)
  AND all(rel IN relationships(path) WHERE type(rel) IN $relationships)
RETURN collect(DISTINCT n) AS nodes, collect(path)[0..$path_limit] AS paths
""".strip()


def _native_seed_cypher(*, schema_state: Neo4jSchemaState, relationships: tuple[str, ...], depth: int) -> str:
    predicate = _seed_predicate(schema_state) or "seed.identity_key = $identity_key"
    if not relationships:
        return f"""
MATCH (seed {{program_id: $program_id}})
WHERE {predicate}
RETURN collect(DISTINCT seed)[0..$limit] AS nodes, [] AS paths
""".strip()
    return f"""
MATCH (seed {{program_id: $program_id}})
WHERE {predicate}
WITH seed LIMIT 1
OPTIONAL MATCH path = (seed)-[*1..{depth}]-(neighbor)
WHERE all(node IN nodes(path) WHERE node.program_id = $program_id)
  AND all(rel IN relationships(path) WHERE type(rel) IN $relationships)
RETURN collect(DISTINCT seed) AS nodes, collect(path)[0..$path_limit] AS paths
""".strip()


def _seed_predicate(schema_state: Neo4jSchemaState) -> str | None:
    predicates = []
    if "identity_key" in schema_state.properties:
        predicates.append("seed.identity_key = $identity_key")
    if "key" in schema_state.properties:
        predicates.append("seed.key = $identity_key")
    if "hostname" in schema_state.properties:
        predicates.append("seed.hostname = $identity_key")
    if "service_key" in schema_state.properties:
        predicates.append("seed.service_key = $identity_key")
    if not predicates:
        return None
    return " OR ".join(predicates)


def _node_order_expression(alias: str, schema_state: Neo4jSchemaState) -> str:
    candidates = [
        "hostname",
        "address",
        "service_key",
        "service_method_normalized_path",
        "normalized_path",
        "route_template",
        "url",
        "key",
        "identity_key",
    ]
    expressions = [f"{alias}.{field}" for field in candidates if field in schema_state.properties]
    if not expressions:
        return f"elementId({alias})"
    return "coalesce(" + ", ".join(expressions + [f"elementId({alias})"]) + ")"


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
    labels = list(node.metadata.get("labels", []))
    primary_label = _primary_label(labels)
    action_properties = _action_target_properties(
        labels=labels,
        primary_label=primary_label,
        properties=node.properties,
        identity=identity_key,
        label=node.label,
    )
    return WorkbenchEntityProfile(
        program_id=program_id,
        entity_key=entity_key,
        profile={
            "type": node.node_type,
            "node_type": node.node_type,
            "label": node.label,
            "caption": node.caption,
            "projection_source": "neo4j_graph_projector_ontology",
            "identity_key": identity_key,
            "labels": labels,
            "canonical_entity_key": node.canonical_entity_key,
            "action_target": node.action_target,
            "safe_query_templates": list(_TEMPLATE_BY_LENS.values()),
        },
        properties=action_properties,
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


async def _neo4j_schema_state(settings: Settings) -> Neo4jSchemaState:
    try:
        rows = await _execute_neo4j_read(
            settings,
            """
CALL db.labels() YIELD label
WITH collect(label) AS labels
CALL db.relationshipTypes() YIELD relationshipType
WITH labels, collect(relationshipType) AS relationships
CALL db.propertyKeys() YIELD propertyKey
RETURN labels, relationships, collect(propertyKey) AS properties
""".strip(),
            {},
        )
    except Exception:
        return Neo4jSchemaState(labels=frozenset(), relationships=frozenset(), properties=frozenset())
    row = rows[0] if rows else {}
    labels = frozenset(str(item) for item in row.get("labels", []) if item)
    relationships = frozenset(str(item) for item in row.get("relationships", []) if item)
    properties = frozenset(str(item) for item in row.get("properties", []) if item)
    return Neo4jSchemaState(labels=labels, relationships=relationships, properties=properties)


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
    action_properties = _action_target_properties(
        labels=labels,
        primary_label=primary_label,
        properties=properties,
        identity=identity,
        label=label,
    )
    canonical_entity_key = _canonical_entity_key(properties)
    action_target = _action_target_payload(
        entity_key=entity_key,
        node_type=node_type,
        primary_label=primary_label,
        label=label,
        properties=action_properties,
    )
    nodes[node_id] = WorkbenchNode(
        id=node_id,
        entity_key=entity_key,
        node_type=node_type,
        label=label,
        caption=_best_caption(properties),
        canonical_entity_key=canonical_entity_key,
        action_target=action_target,
        properties=properties,
        metadata={
            "labels": labels,
            "projection_source": "neo4j_graph_projector_ontology",
            "identity_key": identity,
            "raw_neo4j_shape": "redacted_properties_only",
            "canonical_entity_key": canonical_entity_key,
            "action_bridge": {
                "source": "neo4j_projection_node",
                "resolver": "catalog_target_contracts",
                "status": "canonical_target_available" if action_target.get("values") else "projection_only",
                "target_kind": action_target.get("kind"),
                "values": action_target.get("values", {}),
            },
        },
        visual=_node_visual(primary_label=primary_label, labels=labels, properties=properties),
        badges=[primary_label],
        metrics=_node_metrics(properties),
        evidence_refs=_evidence_refs_from_properties(properties),
        staleness="unknown",
        confidence=0.8,
        source_refs=[{"type": "neo4j", "label": primary_label, "identity_key": identity}],
    )


def _canonical_entity_key(properties: Mapping[str, Any]) -> str | None:
    for field in (
        "canonical_entity_key",
        "surface_entity_key",
        "workbench_entity_key",
        "entity_key",
        "target_entity_key",
    ):
        value = properties.get(field)
        if value not in (None, "", []):
            return str(value)
    return None


def _action_target_payload(
    *,
    entity_key: str,
    node_type: str,
    primary_label: str,
    label: str,
    properties: Mapping[str, Any],
) -> dict[str, Any]:
    values = _action_target_values(primary_label=primary_label, properties=properties, display=label)
    return {
        "entity_key": entity_key,
        "kind": _target_kind(primary_label, node_type),
        "label": primary_label,
        "display": label,
        "source": "neo4j_graph_projector_ontology",
        "values": values,
    }


def _action_target_properties(
    *,
    labels: list[str],
    primary_label: str,
    properties: Mapping[str, Any],
    identity: str,
    label: str,
) -> dict[str, Any]:
    enriched = dict(properties)
    identity_value = _strip_identity_prefix(identity, primary_label)
    service_parts = _service_key_parts(str(enriched.get("service_key") or identity_value or ""))

    if primary_label in {"Host", "Scope"}:
        enriched.setdefault("hostname", identity_value or label)
    if primary_label == "IP":
        enriched.setdefault("address", identity_value or label)
    if primary_label == "CIDR":
        enriched.setdefault("cidr", identity_value or label)
    if primary_label == "ASN":
        enriched.setdefault("asn", identity_value or label)
    if primary_label == "Service":
        enriched.setdefault("service_key", identity_value or label)
    if service_parts:
        hostname, port, scheme = service_parts
        enriched.setdefault("hostname", hostname)
        enriched.setdefault("host", hostname)
        enriched.setdefault("port", port)
        enriched.setdefault("scheme", scheme)
    if primary_label == "Endpoint":
        enriched.setdefault("path", enriched.get("normalized_path") or enriched.get("route_template"))
        enriched.setdefault("method", enriched.get("method"))
        if service_parts:
            hostname, port, scheme = service_parts
            path = str(enriched.get("path") or "/")
            suffix = path if path.startswith("/") else f"/{path}"
            port_suffix = "" if (scheme == "https" and port == "443") or (scheme == "http" and port == "80") else f":{port}"
            enriched.setdefault("url", f"{scheme}://{hostname}{port_suffix}{suffix}")
            enriched.setdefault("base_url", f"{scheme}://{hostname}{port_suffix}")
    if primary_label == "JSFile":
        enriched.setdefault("js_url", enriched.get("url") or enriched.get("source_url") or identity_value)
    enriched.setdefault("identity", identity_value or identity)
    enriched.setdefault("labels", labels)
    return {key: value for key, value in enriched.items() if value not in (None, "", [])}


def _action_target_values(*, primary_label: str, properties: Mapping[str, Any], display: str) -> dict[str, str]:
    values = {
        "identity": _first_text(properties, "identity", "identity_key", "service_key", "service_method_normalized_path"),
        "hostname": _first_text(properties, "hostname", "host", "domain", "name"),
        "address": _first_text(properties, "address", "ip", "ip_address"),
        "cidr": _first_text(properties, "cidr", "cidr_block", "network"),
        "asn": _first_text(properties, "asn", "asn_number", "number"),
        "url": _first_text(properties, "url", "normalized_url"),
        "base_url": _first_text(properties, "base_url", "origin"),
        "path": _first_text(properties, "route_template", "normalized_path", "path"),
        "port": _first_text(properties, "port"),
        "method": _first_text(properties, "method"),
        "js_url": _first_text(properties, "js_url", "source_url", "url"),
    }
    if primary_label in {"Host", "Scope"} and not values["hostname"]:
        values["hostname"] = _hostlike(display)
    if primary_label == "IP" and not values["address"]:
        values["address"] = _hostlike(display)
    if primary_label == "CIDR" and not values["cidr"]:
        values["cidr"] = _hostlike(display)
    if primary_label == "ASN" and not values["asn"]:
        values["asn"] = _hostlike(display)
    if primary_label == "JSFile" and not values["js_url"]:
        values["js_url"] = values.get("url") or _hostlike(display)
    return {key: str(value) for key, value in values.items() if value not in (None, "", [])}


def _target_kind(primary_label: str, node_type: str) -> str:
    aliases = {
        "Host": "host",
        "Scope": "host",
        "IP": "ip",
        "ASN": "asn",
        "CIDR": "cidr",
        "Service": "service",
        "Endpoint": "endpoint",
        "Parameter": "parameter",
        "JSFile": "javascript",
        "SurfaceSnapshot": "surface_snapshot",
        "ActionOutcome": "action_outcome",
    }
    return aliases.get(primary_label, node_type)


def _first_text(properties: Mapping[str, Any], *fields: str) -> str | None:
    for field in fields:
        value = properties.get(field)
        if value not in (None, "", []):
            return str(value)
    return None


def _strip_identity_prefix(identity: str, primary_label: str) -> str:
    text = str(identity).strip()
    prefix = f"{primary_label.lower()}:"
    if text.lower().startswith(prefix):
        return text[len(prefix):]
    return text


def _service_key_parts(value: str) -> tuple[str, str, str] | None:
    # graph-projector service keys use host:port/scheme, for example example.com:443/https.
    match = re.match(r"^(?P<host>.+):(?P<port>\d+)/(?:tcp/)?(?P<scheme>[a-zA-Z][a-zA-Z0-9+.-]*)$", value.strip())
    if not match:
        return None
    return match.group("host"), match.group("port"), match.group("scheme").lower()


def _hostlike(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.startswith("neo4j:"):
        return None
    return text


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
    status: str | None = None,
    details: dict[str, Any] | None = None,
) -> WorkbenchGraph:
    boundary = _neo4j_boundary(surface=f"neo4j_{reason}", template_name=template_name or "none")
    boundary.update(
        {
            "status": status or _message_graph_status(reason),
            "reason": reason,
            "message": message,
            "ui_empty_state": True,
            "render_as_graph_node": False,
        }
    )
    if details:
        boundary["details"] = details
    return WorkbenchGraph(
        program_id=program_id,
        lens=lens,
        seed=seed,
        nodes=[],
        edges=[],
        counts={"nodes": 0, "edges": 0},
        boundary=boundary,
    )


def _message_graph_status(reason: str) -> str:
    if reason in {"seed_required_for_template", "snapshot_seed_required_for_surface_graph_math"}:
        return "seed_required"
    if reason in {"neo4j_template_empty_result", "neo4j_projection_schema_not_ready"}:
        return "empty"
    return "unavailable"

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
