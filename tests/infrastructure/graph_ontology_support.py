from __future__ import annotations

import sys
from pathlib import Path


def graph_ontology():
    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.ontology import (
        GraphNodeDefinition,
        GraphOntology,
        GraphProjectionDefinition,
        GraphRelationshipDefinition,
        default_graph_ontology,
        load_graph_ontology,
    )

    return {
        "GraphNodeDefinition": GraphNodeDefinition,
        "GraphRelationshipDefinition": GraphRelationshipDefinition,
        "GraphProjectionDefinition": GraphProjectionDefinition,
        "GraphOntology": GraphOntology,
        "default_graph_ontology": default_graph_ontology,
        "load_graph_ontology": load_graph_ontology,
    }
