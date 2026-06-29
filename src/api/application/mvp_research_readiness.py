"""Backward-compatible import path for the renamed research readiness gate."""
from __future__ import annotations

from api.application.research_readiness import (
    ResearchReadinessDecision,
    ResearchReadinessGate,
    ResearchReadinessReason,
)

ResearchReadinessGate = ResearchReadinessGate
MvpResearchReadinessGate = ResearchReadinessGate

__all__ = [
    "ResearchReadinessDecision",
    "MvpResearchReadinessGate",
    "ResearchReadinessGate",
    "ResearchReadinessReason",
]
