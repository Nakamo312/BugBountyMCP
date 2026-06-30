"""Deprecated compatibility alias for infrastructure pipeline builder.

Declarative YAML registration resolves concrete runners, parsers, processors,
and ingestors. That makes it infrastructure wiring, not application pipeline
core. New code should import from ``api.infrastructure.pipeline.builder``.
"""
from __future__ import annotations

from api.infrastructure.pipeline.builder import (  # noqa: F401
    build_node,
    register_config_nodes,
    register_manifest_nodes,
    register_yaml_nodes,
)

__all__ = [
    "build_node",
    "register_config_nodes",
    "register_manifest_nodes",
    "register_yaml_nodes",
]
