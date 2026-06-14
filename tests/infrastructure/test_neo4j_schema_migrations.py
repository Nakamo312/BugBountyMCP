from __future__ import annotations

from pathlib import Path


def _graph_schema():
    import sys

    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.ontology import default_graph_ontology
    from graph_projector.schema import build_neo4j_schema_statements, load_neo4j_schema_migration

    return default_graph_ontology, build_neo4j_schema_statements, load_neo4j_schema_migration


def test_schema_builder_creates_node_identity_constraints_for_ontology_labels() -> None:
    default_graph_ontology, build_neo4j_schema_statements, _ = _graph_schema()

    ontology = default_graph_ontology()
    statements = build_neo4j_schema_statements(ontology)
    cypher_by_name = {statement.name: statement.cypher for statement in statements}

    for node in ontology.node_definitions:
        name = f"graph_node_{node.label.lower()}_identity"
        assert name in cypher_by_name
        assert f"CREATE CONSTRAINT {name} IF NOT EXISTS" in cypher_by_name[name]
        assert f"FOR (node:{node.label})" in cypher_by_name[name]
        assert "REQUIRE (node.program_id, node.key) IS UNIQUE" in cypher_by_name[name]


def test_schema_builder_creates_relationship_identity_indexes_not_constraints() -> None:
    default_graph_ontology, build_neo4j_schema_statements, _ = _graph_schema()

    ontology = default_graph_ontology()
    statements = build_neo4j_schema_statements(ontology)
    cypher_by_name = {statement.name: statement.cypher for statement in statements}

    for relationship in ontology.relationship_definitions:
        name = f"graph_rel_{relationship.relationship_type.lower()}_identity"
        assert name in cypher_by_name
        assert f"CREATE INDEX {name} IF NOT EXISTS" in cypher_by_name[name]
        assert f"FOR ()-[rel:{relationship.relationship_type}]-()" in cypher_by_name[name]
        assert "ON (rel.identity_key)" in cypher_by_name[name]
        assert "CREATE CONSTRAINT" not in cypher_by_name[name]


def test_checked_in_migration_file_matches_generated_schema_statements() -> None:
    default_graph_ontology, build_neo4j_schema_statements, load_neo4j_schema_migration = _graph_schema()

    expected = "\n\n".join(
        statement.cypher for statement in build_neo4j_schema_statements(default_graph_ontology())
    )
    actual = load_neo4j_schema_migration().strip()

    assert actual == expected


def test_schema_helper_does_not_import_neo4j_driver() -> None:
    source = Path("services/graph-projector/graph_projector/schema.py").read_text(encoding="utf-8")

    assert "from neo4j" not in source
    assert "import neo4j" not in source
