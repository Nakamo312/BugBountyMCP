from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .ontology import GraphOntology, default_graph_ontology


@dataclass(frozen=True)
class Neo4jSchemaStatement:
    name: str
    cypher: str


def build_neo4j_schema_statements(ontology: GraphOntology | None = None) -> tuple[Neo4jSchemaStatement, ...]:
    graph_ontology = ontology or default_graph_ontology()
    statements: list[Neo4jSchemaStatement] = []

    for node in graph_ontology.node_definitions:
        name = f"graph_node_{_schema_name_part(node.label)}_identity"
        statements.append(
            Neo4jSchemaStatement(
                name=name,
                cypher=(
                    f"CREATE CONSTRAINT {name} IF NOT EXISTS\n"
                    f"FOR (node:{node.label})\n"
                    "REQUIRE (node.program_id, node.key) IS UNIQUE;"
                ),
            )
        )

    for relationship in graph_ontology.relationship_definitions:
        name = f"graph_rel_{_schema_name_part(relationship.relationship_type)}_identity"
        statements.append(
            Neo4jSchemaStatement(
                name=name,
                cypher=(
                    f"CREATE INDEX {name} IF NOT EXISTS\n"
                    f"FOR ()-[rel:{relationship.relationship_type}]-()\n"
                    "ON (rel.identity_key);"
                ),
            )
        )

    return tuple(statements)


def load_neo4j_schema_migration(path: Path | str | None = None) -> str:
    migration_path = (
        Path(path)
        if path is not None
        else Path(__file__).parents[1] / "migrations" / "neo4j" / "V001__graph_identity_schema.cypher"
    )
    return migration_path.read_text(encoding="utf-8")


def render_neo4j_schema_migration(ontology: GraphOntology | None = None) -> str:
    return "\n\n".join(statement.cypher for statement in build_neo4j_schema_statements(ontology))


def _schema_name_part(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
