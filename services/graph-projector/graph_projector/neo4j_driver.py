from __future__ import annotations

from typing import Any

from .settings import GraphProjectorSettings


def create_neo4j_driver(settings: GraphProjectorSettings) -> Any | None:
    """Create a Neo4j driver for the standalone graph projector service."""

    if not settings.neo4j_enabled:
        return None

    try:
        from neo4j import GraphDatabase
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on service image
        raise RuntimeError(
            "Neo4j is enabled but the graph-projector service is missing the neo4j package."
        ) from exc

    return GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
