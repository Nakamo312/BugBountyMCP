from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


_WRITE_CYPHER_RE = re.compile(r"\b(CREATE|DELETE|DETACH|DROP|MERGE|REMOVE|SET)\b", re.IGNORECASE)


@dataclass(frozen=True)
class RenderedGraphQuery:
    cypher: str
    parameters: Mapping[str, object]


@dataclass(frozen=True)
class GraphQueryTemplate:
    name: str
    description: str
    cypher: str
    required_parameters: tuple[str, ...]
    optional_parameters: tuple[str, ...] = ()
    max_rows: int = 100

    def __post_init__(self) -> None:
        _require_text(self.name, "name")
        _require_text(self.description, "description")
        _require_text(self.cypher, "cypher")
        _require_unique_texts(self.required_parameters, "required_parameters")
        _require_unique_texts(self.optional_parameters, "optional_parameters")
        if "gds." in self.cypher.lower():
            raise ValueError("GDS procedures are not allowed in safe graph query templates")
        if not self.is_read_only:
            raise ValueError("graph query template must be read-only")
        if "program_id" not in self.required_parameters:
            raise ValueError("graph query template requires program_id")
        if "$program_id" not in self.cypher:
            raise ValueError("graph query template cypher must reference $program_id")
        if self.max_rows <= 0:
            raise ValueError("max_rows must be positive")

    @property
    def is_read_only(self) -> bool:
        return _WRITE_CYPHER_RE.search(self.cypher) is None

    @property
    def supported_parameters(self) -> tuple[str, ...]:
        return self.required_parameters + self.optional_parameters

    def render(self, parameters: Mapping[str, object]) -> RenderedGraphQuery:
        missing = [name for name in self.required_parameters if name not in parameters]
        if missing:
            raise ValueError(f"missing required graph query parameter: {missing[0]}")
        supported = set(self.supported_parameters)
        unexpected = [name for name in parameters if name not in supported]
        if unexpected:
            raise ValueError(f"unsupported graph query parameter: {unexpected[0]}")

        rendered_parameters = {
            name: _normalize_graph_query_parameter(name, value, required=name in self.required_parameters)
            for name, value in parameters.items()
        }
        if "limit" in self.optional_parameters:
            rendered_parameters["limit"] = _normalize_limit(
                rendered_parameters.get("limit", self.max_rows),
                max_rows=self.max_rows,
            )
        return RenderedGraphQuery(
            cypher=self.cypher,
            parameters=MappingProxyType(rendered_parameters),
        )


class GraphQueryTemplateRegistry:
    def __init__(self, templates: tuple[GraphQueryTemplate, ...]) -> None:
        self._templates = {template.name: template for template in templates}
        if len(self._templates) != len(templates):
            raise ValueError("graph query template names must be unique")

    def get(self, name: str) -> GraphQueryTemplate:
        try:
            return self._templates[name]
        except KeyError as exc:
            raise ValueError(f"unknown graph query template: {name}") from exc

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._templates))


def default_query_template_registry() -> GraphQueryTemplateRegistry:
    return GraphQueryTemplateRegistry(
        (
            GraphQueryTemplate(
                name="endpoint_neighborhood",
                description="Read a bounded neighborhood around one endpoint node.",
                cypher="""
MATCH (endpoint:Endpoint {program_id: $program_id, identity_key: $identity_key})
OPTIONAL MATCH path = (endpoint)-[*1..2]-(neighbor)
WHERE all(node IN nodes(path) WHERE node.program_id = $program_id)
RETURN endpoint, collect(path)[0..$limit] AS paths
LIMIT $limit
""".strip(),
                required_parameters=("program_id", "identity_key"),
                optional_parameters=("limit",),
            ),
            GraphQueryTemplate(
                name="asset_exposure",
                description="Read exposed services and endpoints for one program.",
                cypher="""
MATCH (host:Host {program_id: $program_id})
WITH host ORDER BY host.hostname LIMIT $limit
OPTIONAL MATCH service_path = (host)-[:RESOLVES_TO]->(:IP {program_id: $program_id})-[:EXPOSES_SERVICE]->(:Service {program_id: $program_id})
OPTIONAL MATCH endpoint_path = (host)-[:RESOLVES_TO]->(:IP {program_id: $program_id})-[:EXPOSES_SERVICE]->(:Service {program_id: $program_id})-[:HAS_ENDPOINT]->(:Endpoint {program_id: $program_id})
RETURN host,
       collect(service_path)[0..$limit] AS service_paths,
       collect(endpoint_path)[0..$limit] AS endpoint_paths
LIMIT $limit
""".strip(),
                required_parameters=("program_id",),
                optional_parameters=("limit",),
            ),
            GraphQueryTemplate(
                name="hidden_endpoints_from_js",
                description="Read endpoint candidates connected to JavaScript evidence when those labels exist.",
                cypher="""
MATCH (endpoint:Endpoint {program_id: $program_id})
WHERE endpoint.normalized_path IS NOT NULL
WITH endpoint ORDER BY endpoint.normalized_path LIMIT $limit
OPTIONAL MATCH path = (endpoint)<-[:REFERENCES]-(:JSFile {program_id: $program_id})
RETURN endpoint, collect(path)[0..$limit] AS evidence_paths
LIMIT $limit
""".strip(),
                required_parameters=("program_id",),
                optional_parameters=("limit",),
            ),
            GraphQueryTemplate(
                name="exposed_services_by_technology",
                description="Read exposed services filtered by an optional normalized technology value.",
                cypher="""
MATCH (service:Service {program_id: $program_id})
WHERE $technology IS NULL
   OR any(technology IN coalesce(service.technologies, [])
          WHERE toLower(toString(technology)) = toLower(toString($technology)))
WITH service ORDER BY service.port, service.scheme LIMIT $limit
OPTIONAL MATCH path = (service)-[:HAS_ENDPOINT]->(:Endpoint {program_id: $program_id})
RETURN service, collect(path)[0..$limit] AS endpoint_paths
LIMIT $limit
""".strip(),
                required_parameters=("program_id",),
                optional_parameters=("technology", "limit"),
            ),
            GraphQueryTemplate(
                name="evidence_path",
                description="Read artifact and observation paths that support one graph entity.",
                cypher="""
MATCH (entity {program_id: $program_id, identity_key: $identity_key})
OPTIONAL MATCH path = (artifact:Artifact {program_id: $program_id})
  -[:PRODUCED_OBSERVATION]->(:Observation {program_id: $program_id})
  -[:DESCRIBES]->(entity)
RETURN entity, collect(path)[0..$limit] AS evidence_paths
LIMIT $limit
""".strip(),
                required_parameters=("program_id", "identity_key"),
                optional_parameters=("limit",),
            ),
            GraphQueryTemplate(
                name="action_outcome_experience_neighborhood",
                description="Read action outcome memory with capability/profile and generic feature context.",
                cypher="""
MATCH (outcome:ActionOutcome {program_id: $program_id})
WHERE $outcome_id IS NULL OR outcome.outcome_id = $outcome_id
WITH outcome ORDER BY outcome.finished_at DESC LIMIT $limit
OPTIONAL MATCH feature_path = (outcome)-[:HAS_OUTCOME_FEATURE]->(:OutcomeFeature {program_id: $program_id})
OPTIONAL MATCH capability_path = (outcome)-[:USED_CAPABILITY_PROFILE]->(:CapabilityProfile {program_id: $program_id})
OPTIONAL MATCH run_path = (outcome)-[:OUTCOME_OF_RUN]->(:ToolRun {program_id: $program_id})
RETURN outcome,
       collect(feature_path)[0..$limit] AS feature_paths,
       collect(capability_path)[0..$limit] AS capability_paths,
       collect(run_path)[0..$limit] AS run_paths
LIMIT $limit
""".strip(),
                required_parameters=("program_id",),
                optional_parameters=("outcome_id", "limit"),
            ),
            GraphQueryTemplate(
                name="surface_graph_math",
                description="Read snapshot-local Surface Map shape graph and structural deltas.",
                cypher="""
MATCH (snapshot:SurfaceSnapshot {program_id: $program_id, snapshot_id: $snapshot_id})
OPTIONAL MATCH node_path = (snapshot)-[:HAS_SURFACE_NODE]->(:SurfaceNode {program_id: $program_id})
WITH snapshot, collect(node_path)[0..$limit] AS node_paths
OPTIONAL MATCH delta_path = (snapshot)-[:HAS_SURFACE_DELTA]->(:SurfaceDelta {program_id: $program_id})
RETURN snapshot,
       node_paths,
       collect(delta_path)[0..$limit] AS delta_paths
LIMIT $limit
""".strip(),
                required_parameters=("program_id", "snapshot_id"),
                optional_parameters=("limit",),
            ),
            GraphQueryTemplate(
                name="hypothesis_evidence_paths",
                description="Read evidence paths linked to hypothesis-like graph entities without promoting findings.",
                cypher="""
MATCH (hypothesis {program_id: $program_id})
WHERE ($hypothesis_id IS NULL OR hypothesis.hypothesis_id = $hypothesis_id)
  AND any(label IN labels(hypothesis) WHERE label IN ["Hypothesis", "HypothesisCandidate"])
OPTIONAL MATCH path = (hypothesis)-[:SUPPORTED_BY|:HAS_EVIDENCE|:PRODUCED_EVIDENCE*1..3]-(evidence)
WHERE evidence.program_id = $program_id
RETURN hypothesis, collect(path)[0..$limit] AS evidence_paths
LIMIT $limit
""".strip(),
                required_parameters=("program_id",),
                optional_parameters=("hypothesis_id", "limit"),
            ),
        )
    )


def _require_text(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _require_unique_texts(values: tuple[str, ...], field_name: str) -> None:
    if not values:
        return
    stripped = tuple(value.strip() for value in values)
    if any(not value for value in stripped):
        raise ValueError(f"{field_name} must not contain empty values")
    if len(set(stripped)) != len(stripped):
        raise ValueError(f"{field_name} must be unique")


def _normalize_graph_query_parameter(name: str, value: object, *, required: bool) -> object:
    if value is None:
        if required:
            raise ValueError(f"graph query parameter must not be null: {name}")
        return None
    if name == "limit":
        return value
    if isinstance(value, str):
        normalized = value.strip()
        if required and not normalized:
            raise ValueError(f"graph query parameter must not be empty: {name}")
        if len(normalized) > 2048:
            raise ValueError(f"graph query parameter is too long: {name}")
        return normalized
    if isinstance(value, (bool, int, float)):
        return value
    raise ValueError(f"unsupported graph query parameter type for {name}: {type(value).__name__}")


def _normalize_limit(value: object, *, max_rows: int) -> int:
    if isinstance(value, bool):
        raise ValueError("graph query limit must be a positive integer")
    try:
        limit = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("graph query limit must be a positive integer") from exc
    if limit <= 0:
        raise ValueError("graph query limit must be a positive integer")
    return min(limit, max_rows)
