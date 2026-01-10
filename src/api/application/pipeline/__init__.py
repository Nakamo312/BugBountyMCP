"""Pipeline architecture for event-driven orchestration"""

from .base import PipelineNode, PipelineContext
from .registry import NodeRegistry
from .scope_policy import ScopePolicy
from .bootstrap import build_node_registry

__all__ = [
    "PipelineNode",
    "PipelineContext",
    "NodeRegistry",
    "ScopePolicy",
    "build_node_registry",
]
