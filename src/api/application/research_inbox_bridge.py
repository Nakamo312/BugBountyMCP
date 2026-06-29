"""Compatibility exports for research inbox handoff.

The implementation is split by responsibility:
- ``research_inbox_payload`` parses message payloads.
- ``research_inbox_handoff`` performs idempotent graph handoff.
- ``research_inbox_processor`` owns the claim loop.
- ``research_inbox_models`` carries protocol/result types.
"""
from __future__ import annotations

from api.application.research_inbox_handoff import ResearchInboxBridge, terminal_workflow_status
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
    error_summary,
    hypothesis_request_from_inbox_message,
    research_thread_id_for_inbox_message,
)
from api.application.research_inbox_processor import ResearchInboxProcessor

_terminal_workflow_status = terminal_workflow_status
_error_summary = error_summary

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
    "error_summary",
    "hypothesis_request_from_inbox_message",
    "research_thread_id_for_inbox_message",
    "terminal_workflow_status",
]
