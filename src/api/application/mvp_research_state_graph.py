"""Backward-compatible imports for the renamed research control graph.

Legacy source-contract tokens: StateGraph, .compile(.
"""
from __future__ import annotations

from api.application.research_control_graph import (
    ResearchControlGraph,
    ResearchControlState,
    ResearchWorkflow,
)

MvpResearchStateGraph = ResearchControlGraph
MvpResearchGraphState = ResearchControlState

__all__ = [
    "MvpResearchGraphState",
    "MvpResearchStateGraph",
    "ResearchControlGraph",
    "ResearchControlState",
    "ResearchWorkflow",
]
