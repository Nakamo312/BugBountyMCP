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

from sqlalchemy import bindparam, desc, select

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
from api.infrastructure.adapters.orm import (
    surface_component_analysis_items,
    surface_component_analysis_runs,
    surface_nodes,
)

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
    WorkbenchLens.NEO4J_EXPOSURE: "program_exposure_topology",
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
    "RequestShape",
    "ResponseShape",
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
    "RequestShape": "request_shape",
    "ResponseShape": "response_shape",
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
    "response_family",
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
    "response_family",
    "body_size_bucket",
    "content_type",
    "parser_version",
    "event_type",
    "source_type",
    "created_at",
    "last_seen",
)



_REQUIRED_SCHEMA_BY_TEMPLATE: dict[str, dict[str, set[str]]] = {
    "asset_exposure": {
        "labels": set(),
        "relationships": set(),
        "optional_labels": {"Program", "ASN", "CIDR", "IP", "Host", "Service", "Endpoint", "Parameter", "RequestShape", "ResponseShape", "Artifact", "Observation", "Evidence", "SurfaceNode"},
        "optional_relationships": {"HAS_ASSET", "RESOLVES_TO", "IN_CIDR", "ANNOUNCED_BY", "EXPOSES_SERVICE", "HAS_ENDPOINT", "HAS_PARAM", "HAS_REQUEST_SHAPE", "YIELDS_RESPONSE", "DIFFERS_FROM", "SUPPORTED_BY", "PRODUCED_OBSERVATION", "SUPPORTS_EVIDENCE", "DERIVED_FROM", "REPRESENTS"},
        "island_tolerant": True,
    },
    "program_exposure_topology": {
        "labels": set(),
        "relationships": set(),
        "optional_labels": {"Program", "ASN", "CIDR", "IP", "Host", "Service", "Endpoint", "Parameter", "RequestShape", "ResponseShape", "Artifact", "Observation", "Evidence", "SurfaceNode"},
        "optional_relationships": {"HAS_ASSET", "RESOLVES_TO", "IN_CIDR", "ANNOUNCED_BY", "EXPOSES_SERVICE", "HAS_ENDPOINT", "HAS_PARAM", "HAS_REQUEST_SHAPE", "YIELDS_RESPONSE", "DIFFERS_FROM", "SUPPORTED_BY", "PRODUCED_OBSERVATION", "SUPPORTS_EVIDENCE", "DERIVED_FROM", "REPRESENTS"},
        "island_tolerant": True,
    },
    "endpoint_neighborhood": {"labels": {"Endpoint"}, "relationships": set()},
    "evidence_path": {"labels": {"Artifact", "Observation"}, "relationships": {"PRODUCED_OBSERVATION", "DESCRIBES"}},
    "hidden_endpoints_from_js": {"labels": {"Endpoint", "JSFile"}, "relationships": {"REFERENCES"}},
    "exposed_services_by_technology": {"labels": {"Service", "Endpoint"}, "relationships": {"HAS_ENDPOINT"}},
    "action_outcome_experience_neighborhood": {
        "labels": {"ActionOutcome"},
        "relationships": {"HAS_OUTCOME_FEATURE", "USED_CAPABILITY_PROFILE", "OUTCOME_OF_RUN"},
    },
    "surface_graph_math": {"labels": {"SurfaceSnapshot", "SurfaceNode"}, "relationships": {"HAS_SURFACE_NODE"}},
    "hypothesis_evidence_paths": {"labels": {"Hypothesis", "HypothesisCandidate"}, "relationships": set()},
}


@dataclass(frozen=True)
class Neo4jSchemaState:
    labels: frozenset[str]
    relationships: frozenset[str]

    def missing_for_template(self, template_name: str) -> dict[str, list[str]]:
        required = _REQUIRED_SCHEMA_BY_TEMPLATE.get(template_name, {})
        missing_labels = sorted(set(required.get("labels", set())) - set(self.labels))
        missing_relationships = sorted(set(required.get("relationships", set())) - set(self.relationships))
        missing_optional_labels = sorted(set(required.get("optional_labels", set())) - set(self.labels))
        missing_optional_relationships = sorted(set(required.get("optional_relationships", set())) - set(self.relationships))
        return {
            "labels": missing_labels,
            "relationships": missing_relationships,
            "optional_labels": missing_optional_labels,
            "optional_relationships": missing_optional_relationships,
        }

    def has_any_graph_content(self) -> bool:
        return bool(self.labels or self.relationships)

@dataclass(frozen=True)
class Neo4jTemplateSpec:
    lens: WorkbenchLens
    template_name: str
    label: str


@dataclass(frozen=True)
class SurfaceStructuralSignalIndex:
    lookup: Mapping[str, tuple[dict[str, Any], ...]]
    analysis_run_id: str | None = None
    snapshot_id: str | None = None
    component_count: int = 0
    indexed_signal_count: int = 0

    @property
    def available(self) -> bool:
        return bool(self.lookup)


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
    session_factory: Any | None = None,
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
    schema_state = await _neo4j_schema_state(settings)
    missing_schema = schema_state.missing_for_template(template_name)
    if missing_schema["labels"] or missing_schema["relationships"]:
        status = "empty" if not schema_state.has_any_graph_content() else "preparing"
        return _message_graph(
            program_id=program_id,
            lens=lens,
            seed=seed,
            message=(
                "Relationship graph is not ready for this view yet. "
                "Use the canonical surface map while the graph projection catches up."
            ),
            reason="neo4j_projection_schema_not_ready",
            template_name=template_name,
            status=status,
            details={
                "missing_labels": missing_schema["labels"],
                "missing_relationships": missing_schema["relationships"],
                "missing_optional_labels": missing_schema.get("optional_labels", []),
                "missing_optional_relationships": missing_schema.get("optional_relationships", []),
                "available_labels": sorted(schema_state.labels),
                "available_relationships": sorted(schema_state.relationships),
            },
        )
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
    signal_index = await _load_surface_structural_signal_index(
        session_factory,
        program_id=program_id,
        limit=safe_limit,
    )
    if signal_index.available:
        nodes = _attach_surface_structural_signals(nodes, signal_index)
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
        boundary={
            **_neo4j_boundary(surface=f"neo4j_template_{template_name}", template_name=template_name),
            "topology_contract": _topology_contract_state(template_name, schema_state, missing_schema),
            "structural_signal_overlay": _structural_signal_overlay_state(signal_index),
        },
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


async def _load_surface_structural_signal_index(
    session_factory: Any | None,
    *,
    program_id: UUID,
    limit: int,
) -> SurfaceStructuralSignalIndex:
    if session_factory is None:
        return SurfaceStructuralSignalIndex(lookup={})
    try:
        async with session_factory() as session:
            run = await _latest_surface_component_run(session, program_id)
            if run is None:
                return SurfaceStructuralSignalIndex(lookup={})
            items = await _surface_component_signal_items(session, run["id"], limit=max(1, min(limit, 500)))
            signal_rows = _component_signal_rows(run, items)
            fingerprints = sorted({fingerprint for row in signal_rows for fingerprint in row["node_fingerprints"]})
            surface_rows = await _surface_nodes_for_component_fingerprints(
                session,
                program_id=program_id,
                snapshot_id=run["snapshot_id"],
                fingerprints=fingerprints,
                limit=max(1, min(limit * 20, 5000)),
            )
    except Exception:  # noqa: BLE001 - Workbench must keep Neo4j graph readable if Postgres signals lag.
        return SurfaceStructuralSignalIndex(lookup={})

    lookup: dict[str, list[dict[str, Any]]] = {}
    surface_rows_by_fingerprint = {str(row["node_fingerprint"]): row for row in surface_rows if row.get("node_fingerprint")}
    for signal_row in signal_rows:
        for fingerprint in signal_row["node_fingerprints"]:
            _append_signal(lookup, f"surface_node_fingerprint:{fingerprint}", signal_row["signal"])
            surface_row = surface_rows_by_fingerprint.get(fingerprint)
            if surface_row:
                for key in _surface_row_signal_lookup_keys(surface_row):
                    _append_signal(lookup, key, signal_row["signal"])
    frozen_lookup = {key: tuple(_dedupe_signals(values)) for key, values in lookup.items() if values}
    return SurfaceStructuralSignalIndex(
        lookup=frozen_lookup,
        analysis_run_id=str(run["id"]),
        snapshot_id=str(run["snapshot_id"]),
        component_count=len(items),
        indexed_signal_count=sum(len(values) for values in frozen_lookup.values()),
    )


async def _latest_surface_component_run(session: Any, program_id: UUID) -> Mapping[str, Any] | None:
    statement = (
        select(
            surface_component_analysis_runs.c.id,
            surface_component_analysis_runs.c.program_id,
            surface_component_analysis_runs.c.snapshot_id,
            surface_component_analysis_runs.c.algorithm,
            surface_component_analysis_runs.c.algorithm_version,
            surface_component_analysis_runs.c.created_at,
        )
        .where(surface_component_analysis_runs.c.program_id == bindparam("program_id"))
        .order_by(surface_component_analysis_runs.c.created_at.desc(), surface_component_analysis_runs.c.id.desc())
        .limit(1)
    )
    result = await session.execute(statement, {"program_id": program_id})
    return result.mappings().one_or_none()


async def _surface_component_signal_items(session: Any, analysis_run_id: UUID, *, limit: int) -> list[Mapping[str, Any]]:
    statement = (
        select(
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
        )
        .where(surface_component_analysis_items.c.analysis_run_id == bindparam("analysis_run_id"))
        .order_by(
            desc(surface_component_analysis_items.c.exploration_priority_score).nulls_last(),
            desc(surface_component_analysis_items.c.structural_pressure_score).nulls_last(),
            surface_component_analysis_items.c.component_id.asc(),
        )
        .limit(limit)
    )
    result = await session.execute(statement, {"analysis_run_id": analysis_run_id})
    return list(result.mappings().all())


async def _surface_nodes_for_component_fingerprints(
    session: Any,
    *,
    program_id: UUID,
    snapshot_id: UUID,
    fingerprints: list[str],
    limit: int,
) -> list[Mapping[str, Any]]:
    if not fingerprints:
        return []
    statement = (
        select(
            surface_nodes.c.node_fingerprint,
            surface_nodes.c.node_type,
            surface_nodes.c.host,
            surface_nodes.c.path,
            surface_nodes.c.route_template,
            surface_nodes.c.method,
        )
        .where(surface_nodes.c.program_id == bindparam("program_id"))
        .where(surface_nodes.c.snapshot_id == bindparam("snapshot_id"))
        .where(surface_nodes.c.node_fingerprint.in_(bindparam("fingerprints", expanding=True)))
        .limit(limit)
    )
    result = await session.execute(
        statement,
        {"program_id": program_id, "snapshot_id": snapshot_id, "fingerprints": fingerprints[:limit]},
    )
    return list(result.mappings().all())


def _component_signal_rows(run: Mapping[str, Any], items: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for item in items:
        fingerprints = _component_node_fingerprints(item)
        if not fingerprints:
            continue
        signal = _component_structural_signal(run, item)
        if signal:
            rows.append({"node_fingerprints": fingerprints, "signal": signal})
    return rows


def _component_node_fingerprints(item: Mapping[str, Any]) -> tuple[str, ...]:
    metrics = _safe_mapping(item.get("metrics_json"))
    profile = _safe_mapping(metrics.get("profile"))
    raw_fingerprints = profile.get("node_fingerprints") or metrics.get("node_fingerprints") or ()
    return tuple(str(value) for value in raw_fingerprints if value)


def _component_structural_signal(run: Mapping[str, Any], item: Mapping[str, Any]) -> dict[str, Any]:
    component_id = int(item["component_id"])
    scores = {
        "structural_pressure": _optional_int(item.get("structural_pressure_score")),
        "drift": _optional_int(item.get("drift_score")),
        "bridge_pressure": _optional_int(item.get("bridge_pressure_score")),
        "outlier_pressure": _optional_int(item.get("outlier_score")),
        "coverage": _optional_int(item.get("coverage_score")),
        "exploration_priority": _optional_int(item.get("exploration_priority_score")),
    }
    present_scores = {key: value for key, value in scores.items() if value is not None}
    if not present_scores:
        return {}
    return {
        "type": "surface_component_structural_signal",
        "source": "surface_component_analysis_items",
        "component_id": component_id,
        "analysis_run_id": str(run["id"]),
        "snapshot_id": str(run["snapshot_id"]),
        "algorithm": run.get("algorithm"),
        "algorithm_version": run.get("algorithm_version"),
        "score": max(int(value) for value in present_scores.values()),
        "scores": present_scores,
        "node_count": int(item.get("node_count") or 0),
        "changed_node_count": int(item.get("changed_node_count") or 0),
        "action_candidate_count": int(item.get("action_candidate_count") or 0),
        "evidence_ref": {
            "type": "surface_component_analysis_item",
            "id": f"{run['id']}:{component_id}",
            "analysis_run_id": str(run["id"]),
            "component_id": component_id,
        },
        "semantics": "advisory_structural_signal_not_finding_or_verdict",
    }


def _attach_surface_structural_signals(
    nodes: dict[str, WorkbenchNode],
    signal_index: SurfaceStructuralSignalIndex,
) -> dict[str, WorkbenchNode]:
    if not signal_index.available:
        return nodes
    enriched: dict[str, WorkbenchNode] = {}
    for node_id, node in nodes.items():
        signals = _signals_for_node(node, signal_index)
        if not signals:
            enriched[node_id] = node
            continue
        max_score = max(int(signal.get("score") or 0) for signal in signals)
        metadata = dict(node.metadata)
        metadata["structural_signals"] = signals
        metadata["structural_signal_overlay"] = {
            "source": "surface_component_analysis",
            "analysis_run_id": signal_index.analysis_run_id,
            "snapshot_id": signal_index.snapshot_id,
            "match": "surface_node_membership_or_canonical_surface_key",
            "island_tolerant": True,
        }
        metrics = dict(node.metrics)
        metrics["max_structural_signal_score"] = max_score
        badges = list(node.badges)
        if "GDS" not in badges:
            badges.append("GDS")
        if max_score >= 70 and "attention" not in badges:
            badges.append("attention")
        evidence_refs = [*node.evidence_refs, *[signal["evidence_ref"] for signal in signals if signal.get("evidence_ref")]][:8]
        visual = dict(node.visual)
        visual.setdefault("signal_score", max_score)
        visual.setdefault("signal_badge", _dominant_signal_type(signals))
        enriched[node_id] = node.model_copy(
            update={
                "metadata": metadata,
                "metrics": metrics,
                "badges": badges,
                "evidence_refs": _dedupe_refs(evidence_refs),
                "visual": visual,
                "confidence": max(node.confidence, min(max_score / 100.0, 1.0)),
            }
        )
    return enriched


def _signals_for_node(node: WorkbenchNode, signal_index: SurfaceStructuralSignalIndex) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    for key in _node_signal_lookup_keys(node):
        signals.extend(signal_index.lookup.get(key, ()))
    return _dedupe_signals(signals)[:6]


def _node_signal_lookup_keys(node: WorkbenchNode) -> tuple[str, ...]:
    properties = node.properties or {}
    keys: list[str] = []
    node_fingerprint = properties.get("node_fingerprint")
    if node_fingerprint:
        keys.append(f"surface_node_fingerprint:{node_fingerprint}")
    canonical = node.canonical_entity_key or properties.get("canonical_entity_key")
    if canonical:
        keys.append(str(canonical))
    host = _first_text(properties, "hostname", "host", "domain", "name")
    if host:
        keys.append(f"host:{host}")
    endpoint_key = _endpoint_surface_lookup_key(properties)
    if endpoint_key:
        keys.append(endpoint_key)
    endpoint_from_identity = _endpoint_surface_lookup_key_from_identity(str(properties.get("endpoint_key") or properties.get("identity_key") or ""))
    if endpoint_from_identity:
        keys.append(endpoint_from_identity)
    return tuple(dict.fromkeys(keys))


def _surface_row_signal_lookup_keys(row: Mapping[str, Any]) -> tuple[str, ...]:
    keys: list[str] = []
    fingerprint = row.get("node_fingerprint")
    if fingerprint:
        keys.append(f"surface_node_fingerprint:{fingerprint}")
    host = row.get("host")
    if host:
        keys.append(f"host:{host}")
    method = row.get("method")
    route = row.get("route_template") or row.get("path")
    if host and method and route:
        keys.append(f"surface:{host}:{str(method).upper()}:{route}")
    return tuple(dict.fromkeys(str(key) for key in keys if key))


def _endpoint_surface_lookup_key(properties: Mapping[str, Any]) -> str | None:
    method = properties.get("method")
    route = properties.get("route_template") or properties.get("normalized_path") or properties.get("path")
    host = properties.get("hostname") or properties.get("host")
    if not host:
        service_parts = _service_key_parts(str(properties.get("service_key") or ""))
        if service_parts:
            host = service_parts[0]
    if host and method and route:
        return f"surface:{host}:{str(method).upper()}:{route}"
    return None


def _endpoint_surface_lookup_key_from_identity(identity: str) -> str | None:
    # Endpoint-like identity uses service_key:METHOD:/path. Parameter and request
    # shapes keep that endpoint prefix before their own suffixes; extracting this
    # keeps signal attachment advisory and island-friendly without requiring a
    # persisted SurfaceNode -> Endpoint edge.
    match = re.match(r"^(?P<service>.+:\\d+/(?:tcp/)?[A-Za-z][A-Za-z0-9+.-]*):(?P<method>[A-Z]+):(?P<path>/[^:]*).*$", identity)
    if not match:
        return None
    service_parts = _service_key_parts(match.group("service"))
    if not service_parts:
        return None
    host, _port, _scheme = service_parts
    return f"surface:{host}:{match.group('method')}:{match.group('path')}"


def _append_signal(lookup: dict[str, list[dict[str, Any]]], key: str | None, signal: dict[str, Any]) -> None:
    if key and signal:
        lookup.setdefault(str(key), []).append(signal)


def _dedupe_signals(signals: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for signal in signals:
        key = f"{signal.get('analysis_run_id')}:{signal.get('component_id')}:{signal.get('type')}"
        deduped.setdefault(key, signal)
    return sorted(deduped.values(), key=lambda item: int(item.get("score") or 0), reverse=True)


def _dedupe_refs(refs: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for ref in refs:
        key = f"{ref.get('type')}:{ref.get('id')}"
        deduped.setdefault(key, ref)
    return list(deduped.values())[:8]


def _dominant_signal_type(signals: list[dict[str, Any]]) -> str | None:
    if not signals:
        return None
    scores = _safe_mapping(signals[0].get("scores"))
    if not scores:
        return str(signals[0].get("type") or "structural_signal")
    return max(scores.items(), key=lambda item: int(item[1] or 0))[0]


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _structural_signal_overlay_state(signal_index: SurfaceStructuralSignalIndex) -> dict[str, Any]:
    return {
        "source": "surface_component_analysis_items",
        "available": signal_index.available,
        "analysis_run_id": signal_index.analysis_run_id,
        "snapshot_id": signal_index.snapshot_id,
        "component_count": signal_index.component_count,
        "indexed_signal_count": signal_index.indexed_signal_count,
        "island_tolerant": True,
        "semantics": "advisory_structural_signal_not_finding_or_verdict",
    }


async def _neo4j_schema_state(settings: Settings) -> Neo4jSchemaState:
    try:
        rows = await _execute_neo4j_read(
            settings,
            """
CALL db.labels() YIELD label
WITH collect(label) AS labels
CALL db.relationshipTypes() YIELD relationshipType
RETURN labels, collect(relationshipType) AS relationships
""".strip(),
            {},
        )
    except Exception:
        return Neo4jSchemaState(labels=frozenset(), relationships=frozenset())
    row = rows[0] if rows else {}
    labels = frozenset(str(item) for item in row.get("labels", []) if item)
    relationships = frozenset(str(item) for item in row.get("relationships", []) if item)
    return Neo4jSchemaState(labels=labels, relationships=relationships)


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
    topology = _topology_metadata(primary_label=primary_label, properties=properties)
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
            "topology": topology,
            "action_bridge": {
                "source": "neo4j_projection_node",
                "resolver": "catalog_target_contracts",
                "status": "canonical_target_available" if action_target.get("values") else "projection_only",
                "target_kind": action_target.get("kind"),
                "values": action_target.get("values", {}),
            },
        },
        badges=["Neo4j", primary_label, topology["lane"]],
        metrics={**_node_metrics(properties), "topology_rank": topology["rank"]},
        evidence_refs=_evidence_refs_from_properties(properties),
        staleness="unknown",
        confidence=0.8,
        source_refs=[{"type": "neo4j", "label": primary_label, "identity_key": identity}],
    )




def _topology_contract_state(
    template_name: str,
    schema_state: Neo4jSchemaState,
    missing_schema: dict[str, list[str]],
) -> dict[str, Any]:
    required = _REQUIRED_SCHEMA_BY_TEMPLATE.get(template_name, {})
    return {
        "template": template_name,
        "island_tolerant": bool(required.get("island_tolerant", False)),
        "required_labels": sorted(required.get("labels", set())),
        "required_relationships": sorted(required.get("relationships", set())),
        "optional_labels": sorted(required.get("optional_labels", set())),
        "optional_relationships": sorted(required.get("optional_relationships", set())),
        "missing_optional_labels": missing_schema.get("optional_labels", []),
        "missing_optional_relationships": missing_schema.get("optional_relationships", []),
        "available_labels": sorted(schema_state.labels),
        "available_relationships": sorted(schema_state.relationships),
    }


_TOPOLOGY_LANES: dict[str, tuple[str, int]] = {
    "Program": ("program", 0),
    "ASN": ("network", 10),
    "CIDR": ("network", 20),
    "IP": ("network", 30),
    "Host": ("asset", 40),
    "Service": ("service", 50),
    "Endpoint": ("surface", 60),
    "Parameter": ("surface", 70),
    "RequestShape": ("request", 80),
    "ResponseShape": ("response", 90),
    "Observation": ("evidence", 100),
    "Evidence": ("evidence", 110),
    "Artifact": ("evidence", 120),
    "SurfaceNode": ("surface-map", 130),
    "SurfaceSnapshot": ("surface-map", 140),
    "SurfaceFingerprint": ("surface-map", 150),
    "SurfaceDelta": ("surface-map", 160),
}


def _topology_metadata(*, primary_label: str, properties: Mapping[str, Any]) -> dict[str, Any]:
    lane, rank = _TOPOLOGY_LANES.get(primary_label, ("other", 900))
    collapse_key = properties.get("collapse_key") or properties.get("service_key") or properties.get("endpoint_key") or properties.get("identity_key")
    return {
        "lane": lane,
        "rank": rank,
        "collapse_key": str(collapse_key) if collapse_key not in (None, "", []) else None,
        "visual_role": primary_label,
    }


def _relationship_weight(rel_type: str, properties: Mapping[str, Any]) -> float:
    if properties.get("weight") not in (None, "", []):
        try:
            return float(properties["weight"])
        except (TypeError, ValueError):
            pass
    return {
        "HAS_ASSET": 0.25,
        "RESOLVES_TO": 2.0,
        "IN_CIDR": 1.8,
        "ANNOUNCED_BY": 1.6,
        "EXPOSES_SERVICE": 2.0,
        "HAS_ENDPOINT": 2.2,
        "HAS_PARAM": 1.4,
        "HAS_REQUEST_SHAPE": 1.5,
        "YIELDS_RESPONSE": 1.7,
        "MUTATES": 1.3,
        "DIFFERS_FROM": 1.1,
        "SUPPORTED_BY": 1.0,
        "SUPPORTS_EVIDENCE": 1.0,
        "DERIVED_FROM": 0.8,
        "PRODUCED_OBSERVATION": 0.8,
        "REPRESENTS": 1.2,
    }.get(rel_type, 1.0)


def _relationship_caption(rel_type: str, properties: Mapping[str, Any]) -> str | None:
    caption = _best_caption(properties)
    if caption:
        return caption
    return {
        "HAS_ASSET": "program-owned asset anchor",
        "RESOLVES_TO": "DNS/observation resolution",
        "IN_CIDR": "network membership",
        "ANNOUNCED_BY": "BGP announcement",
        "EXPOSES_SERVICE": "observable service exposure",
        "HAS_ENDPOINT": "HTTP/API surface",
        "HAS_PARAM": "request parameter shape",
        "HAS_REQUEST_SHAPE": "safe request shape",
        "YIELDS_RESPONSE": "observed response shape",
        "MUTATES": "request-shape mutation",
        "DIFFERS_FROM": "response-shape delta",
        "SUPPORTED_BY": "supported by observation",
        "SUPPORTS_EVIDENCE": "observation evidence claim",
        "DERIVED_FROM": "derived from artifact",
        "PRODUCED_OBSERVATION": "artifact produced observation",
        "REPRESENTS": "surface node bridge",
    }.get(rel_type)

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
        enriched.setdefault("display_label", enriched.get("display_label") or _endpoint_context_label(enriched, identity_value or label))
        if service_parts:
            hostname, port, scheme = service_parts
            path = str(enriched.get("path") or "/")
            suffix = path if path.startswith("/") else f"/{path}"
            port_suffix = "" if (scheme == "https" and port == "443") or (scheme == "http" and port == "80") else f":{port}"
            enriched.setdefault("url", f"{scheme}://{hostname}{port_suffix}{suffix}")
            enriched.setdefault("base_url", f"{scheme}://{hostname}{port_suffix}")
    if primary_label == "RequestShape":
        enriched.setdefault("path", enriched.get("normalized_path") or enriched.get("route_template"))
        enriched.setdefault("method", enriched.get("method"))
        enriched.setdefault("display_label", enriched.get("display_label") or _endpoint_context_label(enriched, identity_value or label))
    if primary_label == "ResponseShape":
        enriched.setdefault("display_label", enriched.get("display_label") or identity_value or label)
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
    if primary_label == "RequestShape" and not values["path"]:
        values["path"] = _first_text(properties, "normalized_path", "path")
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
        "RequestShape": "request_shape",
        "ResponseShape": "response_shape",
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


def _endpoint_context_label(properties: Mapping[str, Any], fallback: str) -> str:
    method = properties.get("method")
    path = properties.get("route_template") or properties.get("normalized_path") or properties.get("path")
    host = properties.get("hostname") or properties.get("host")
    port = properties.get("port")
    if method and path and host and port:
        return f"{method} {path} @ {host}:{port}"
    if method and path and host:
        return f"{method} {path} @ {host}"
    return str(fallback)


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
        caption=_relationship_caption(rel_type, properties),
        weight=_relationship_weight(rel_type, properties),
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
    display_label = properties.get("display_label")
    if display_label not in (None, "", []):
        return str(display_label)
    method = properties.get("method")
    path = properties.get("route_template") or properties.get("normalized_path") or properties.get("path")
    if method and path:
        return _endpoint_context_label(properties, f"{method} {path}")
    if properties.get("scheme") and properties.get("port"):
        host = properties.get("hostname") or properties.get("host") or properties.get("address")
        suffix = f" @ {host}" if host else ""
        return f"{properties.get('scheme')}:{properties.get('port')}{suffix}"
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
        "body_size_bytes",
        "parameter_count",
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


def _safe_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
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
