"""DTOs for infrastructure graph visualization"""
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel


class GraphNodeDTO(BaseModel):
    id: str
    type: str
    label: str
    data: Dict[str, Any] = {}


class GraphEdgeDTO(BaseModel):
    source: str
    target: str
    type: str = "default"


class InfrastructureGraphDTO(BaseModel):
    nodes: List[GraphNodeDTO]
    edges: List[GraphEdgeDTO]
    stats: Dict[str, int] = {}
