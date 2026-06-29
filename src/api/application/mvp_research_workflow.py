"""Backward-compatible imports for the renamed research pass."""
from __future__ import annotations

from api.application.research_pass import (
    HypothesisBuilder,
    HypothesisCritic,
    ReportDraftBuilder,
    ResearchPass,
    ResearchPassItem,
    ResearchPassResult,
    ResearchPassSummary,
    summarize_research_pass,
)

MvpResearchItem = ResearchPassItem
MvpResearchResult = ResearchPassResult
MvpResearchWorkflow = ResearchPass

__all__ = [
    "HypothesisBuilder",
    "HypothesisCritic",
    "MvpResearchItem",
    "MvpResearchResult",
    "MvpResearchWorkflow",
    "ReportDraftBuilder",
    "ResearchPass",
    "ResearchPassItem",
    "ResearchPassResult",
    "ResearchPassSummary",
    "summarize_research_pass",
]
