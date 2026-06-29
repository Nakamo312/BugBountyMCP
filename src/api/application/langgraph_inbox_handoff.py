"""Backward-compatible import aliases for the research inbox bridge."""
from __future__ import annotations

from api.application.research_inbox_handoff import ResearchInboxBridge
from api.application.research_inbox_models import (
    AgentInboxAckStore,
    AgentInboxClaimStore,
    AgentInboxFailureStore,
    AgentWorkflowRunStatusReader,
    ResearchExecutionGraph,
    ResearchInboxBridgeResult,
    ResearchInboxProcessorSweep,
)
from api.application.research_inbox_payload import (
    hypothesis_request_from_inbox_message,
    research_thread_id_for_inbox_message,
)
from api.application.research_inbox_processor import ResearchInboxProcessor

# Compatibility names for older imports.
MvpResearchGraph = ResearchExecutionGraph
InboxLangGraphHandoffResult = ResearchInboxBridgeResult
MvpResearchInboxProcessor = ResearchInboxProcessor
MvpResearchInboxProcessorSweep = ResearchInboxProcessorSweep
MvpResearchInboxHandoff = ResearchInboxBridge
langgraph_thread_id_for_inbox_message = research_thread_id_for_inbox_message

__all__ = [
    "AgentInboxAckStore",
    "AgentInboxClaimStore",
    "AgentInboxFailureStore",
    "AgentWorkflowRunStatusReader",
    "ResearchExecutionGraph",
    "ResearchInboxBridge",
    "ResearchInboxBridgeResult",
    "ResearchInboxProcessor",
    "ResearchInboxProcessorSweep",
    "hypothesis_request_from_inbox_message",
    "research_thread_id_for_inbox_message",
    "MvpResearchGraph",
    "InboxLangGraphHandoffResult",
    "MvpResearchInboxProcessor",
    "MvpResearchInboxProcessorSweep",
    "MvpResearchInboxHandoff",
    "langgraph_thread_id_for_inbox_message",
]
