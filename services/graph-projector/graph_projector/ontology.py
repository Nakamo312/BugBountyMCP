from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


GraphLayer = Literal["surface", "lineage"]
GraphOntologyLevel = Literal[
    "L0_CORE",
    "L1_INFRASTRUCTURE",
    "L2_WEB_API",
    "L3_TECH_SUPPLY_CHAIN",
    "L4_OSINT_CLOUD_EXPOSURE",
    "L5_RESEARCH",
]
GraphMaturity = Literal["candidate", "experimental", "stable", "deprecated"]


class GraphPromotionCriteria(BaseModel):
    model_config = ConfigDict(frozen=True)

    producer: str = Field(min_length=1)
    query_template: str = Field(min_length=1)
    idempotent_upsert_test: str = Field(min_length=1)
    evidence_lineage_example: str = Field(min_length=1)
    identity_key: str = Field(min_length=1)
    constraints: str = Field(min_length=1)
    graph_facts: str = Field(min_length=1)
    rebuild_support: str = Field(min_length=1)
    dashboard_or_search_representation: str = Field(min_length=1)

    @field_validator(
        "producer",
        "query_template",
        "idempotent_upsert_test",
        "evidence_lineage_example",
        "identity_key",
        "constraints",
        "graph_facts",
        "rebuild_support",
        "dashboard_or_search_representation",
    )
    @classmethod
    def _strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be empty")
        return stripped


class GraphIdentityPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    graph_key: str = Field(min_length=1)
    source_properties: tuple[str, ...]
    key_policy: str = Field(min_length=1)

    @field_validator("graph_key", "key_policy")
    @classmethod
    def _strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be empty")
        return stripped

    @field_validator("source_properties")
    @classmethod
    def _strip_source_properties(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        stripped_values = tuple(value.strip() for value in values)
        if not stripped_values:
            raise ValueError("source_properties must not be empty")
        if any(not value for value in stripped_values):
            raise ValueError("source_properties must not contain empty values")
        return stripped_values


class _DefinitionBase(BaseModel):
    model_config = ConfigDict(frozen=True)

    description: str = Field(min_length=1)

    @field_validator("description")
    @classmethod
    def _strip_description(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("description must not be empty")
        return stripped

    @staticmethod
    def _strip_tuple_values(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
        stripped_values = tuple(value.strip() for value in values)
        if any(not value for value in stripped_values):
            raise ValueError(f"{field_name} must not contain empty values")
        return stripped_values


class _GovernedDefinitionBase(_DefinitionBase):
    level: GraphOntologyLevel
    maturity: GraphMaturity
    promotion: GraphPromotionCriteria | None = None
    sources: tuple[str, ...]
    parser_outputs: tuple[str, ...]
    query_templates: tuple[str, ...]
    property_vs_node_rationale: str = Field(min_length=1)
    retention: str = Field(min_length=1)
    sensitivity: str = Field(min_length=1)
    confidence_policy: str = Field(min_length=1)
    stale_policy: str = Field(min_length=1)

    @field_validator(
        "sources",
        "parser_outputs",
        "query_templates",
    )
    @classmethod
    def _strip_governance_tuple_fields(cls, values: tuple[str, ...], info) -> tuple[str, ...]:
        stripped_values = cls._strip_tuple_values(values, info.field_name)
        if not stripped_values:
            raise ValueError(f"{info.field_name} must not be empty")
        return stripped_values

    @field_validator(
        "property_vs_node_rationale",
        "retention",
        "sensitivity",
        "confidence_policy",
        "stale_policy",
    )
    @classmethod
    def _strip_governance_text_fields(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be empty")
        return stripped

    @model_validator(mode="after")
    def _stable_requires_promotion_criteria(self) -> "_GovernedDefinitionBase":
        if self.maturity == "stable" and self.promotion is None:
            raise ValueError("stable graph ontology definitions require promotion criteria")
        return self


class GraphNodeDefinition(_GovernedDefinitionBase):
    label: str = Field(min_length=1)
    layer: GraphLayer
    identity: GraphIdentityPolicy
    identity_properties: tuple[str, ...]
    required_properties: tuple[str, ...] = ("program_id",)
    optional_properties: tuple[str, ...] = ()
    source_references: tuple[str, ...] = ()
    projections: tuple[str, ...] = ()

    @field_validator(
        "identity_properties",
        "required_properties",
        "optional_properties",
        "source_references",
        "projections",
    )
    @classmethod
    def _strip_tuple_fields(cls, values: tuple[str, ...], info) -> tuple[str, ...]:
        return cls._strip_tuple_values(values, info.field_name)

    @field_validator("label")
    @classmethod
    def _strip_label(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("label must not be empty")
        return stripped

    @model_validator(mode="after")
    def _requires_identity_and_required_properties(self) -> "GraphNodeDefinition":
        if not self.identity_properties:
            raise ValueError("node definition requires identity_properties")
        missing = set(self.identity_properties).difference(self.required_properties)
        if missing:
            raise ValueError("identity_properties must be included in required_properties")
        missing_sources = set(self.identity.source_properties).difference(self.required_properties)
        if missing_sources:
            raise ValueError("identity source_properties must be included in required_properties")
        return self


class GraphRelationshipDefinition(_GovernedDefinitionBase):
    relationship_type: str = Field(min_length=1)
    source_labels: tuple[str, ...]
    target_labels: tuple[str, ...]
    required_properties: tuple[str, ...] = ("program_id",)
    optional_properties: tuple[str, ...] = ()
    source_references: tuple[str, ...] = ()
    projections: tuple[str, ...] = ()

    @field_validator(
        "source_labels",
        "target_labels",
        "required_properties",
        "optional_properties",
        "source_references",
        "projections",
    )
    @classmethod
    def _strip_tuple_fields(cls, values: tuple[str, ...], info) -> tuple[str, ...]:
        return cls._strip_tuple_values(values, info.field_name)

    @field_validator("relationship_type")
    @classmethod
    def _strip_relationship_type(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("relationship_type must not be empty")
        return stripped

    @model_validator(mode="after")
    def _requires_endpoints(self) -> "GraphRelationshipDefinition":
        if not self.source_labels:
            raise ValueError("relationship definition requires source_labels")
        if not self.target_labels:
            raise ValueError("relationship definition requires target_labels")
        return self


class GraphProjectionDefinition(_DefinitionBase):
    name: str = Field(min_length=1)
    level: GraphOntologyLevel
    query_templates: tuple[str, ...]
    expected_output: str = Field(min_length=1)
    node_labels: tuple[str, ...]
    relationship_types: tuple[str, ...]
    use_case: str = Field(min_length=1)
    version: int = Field(default=1, ge=1)

    @field_validator("node_labels", "relationship_types", "query_templates")
    @classmethod
    def _strip_tuple_fields(cls, values: tuple[str, ...], info) -> tuple[str, ...]:
        return cls._strip_tuple_values(values, info.field_name)

    @field_validator("name", "use_case", "expected_output")
    @classmethod
    def _strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be empty")
        return stripped

    @model_validator(mode="after")
    def _requires_projection_scope(self) -> "GraphProjectionDefinition":
        if not self.node_labels:
            raise ValueError("projection definition requires node_labels")
        if not self.relationship_types:
            raise ValueError("projection definition requires relationship_types")
        return self


class GraphOntology(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    nodes: tuple[GraphNodeDefinition, ...]
    relationships: tuple[GraphRelationshipDefinition, ...]
    projections: tuple[GraphProjectionDefinition, ...]

    @property
    def node_definitions(self) -> tuple[GraphNodeDefinition, ...]:
        return self.nodes

    @property
    def relationship_definitions(self) -> tuple[GraphRelationshipDefinition, ...]:
        return self.relationships

    @property
    def projection_definitions(self) -> tuple[GraphProjectionDefinition, ...]:
        return self.projections

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("ontology name must not be empty")
        return stripped

    @model_validator(mode="after")
    def _validate_references(self) -> "GraphOntology":
        if not self.nodes:
            raise ValueError("ontology requires nodes")
        if not self.relationships:
            raise ValueError("ontology requires relationships")
        if not self.projections:
            raise ValueError("ontology requires projections")

        node_labels = [definition.label for definition in self.nodes]
        relationship_types = [definition.relationship_type for definition in self.relationships]
        projection_names = [definition.name for definition in self.projections]

        if len(node_labels) != len(set(node_labels)):
            raise ValueError("node labels must be unique")
        if len(relationship_types) != len(set(relationship_types)):
            raise ValueError("relationship types must be unique")
        if len(projection_names) != len(set(projection_names)):
            raise ValueError("projection names must be unique")

        known_labels = set(node_labels)
        known_relationships = set(relationship_types)
        known_projections = set(projection_names)

        for relationship in self.relationships:
            if set(relationship.source_labels).difference(known_labels):
                raise ValueError("relationship source_labels must reference known node labels")
            if set(relationship.target_labels).difference(known_labels):
                raise ValueError("relationship target_labels must reference known node labels")
            if set(relationship.projections).difference(known_projections):
                raise ValueError("relationship projections must reference known projections")

        for node in self.nodes:
            if set(node.projections).difference(known_projections):
                raise ValueError("node projections must reference known projections")

        for projection in self.projections:
            if set(projection.node_labels).difference(known_labels):
                raise ValueError("projection node_labels must reference known node labels")
            if set(projection.relationship_types).difference(known_relationships):
                raise ValueError("projection relationship_types must reference known relationships")

        return self


def load_graph_ontology(path: Path | str | None = None) -> GraphOntology:
    ontology_path = Path(path) if path is not None else Path(__file__).with_name("ontology.yaml")
    with ontology_path.open("r", encoding="utf-8") as handle:
        raw: Any = yaml.safe_load(handle)
    if not isinstance(raw, dict):
        raise ValueError("graph ontology yaml must contain a mapping")
    return GraphOntology.model_validate(raw)


def default_graph_ontology() -> GraphOntology:
    return load_graph_ontology()
