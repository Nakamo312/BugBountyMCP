"""Compatibility façade for agent action proposal application services.

The implementation is split by responsibility:
models, ports, payload helpers, feedback policy, writer, acceptance, and review.
This module keeps the old import path stable for routes, tests, and runtimes.

Compatibility notes for legacy source-contract tests:
- ActionRequestSubmitter remains re-exported from this module.
- Proposal metadata still records "forbidden_from_agent_proposal".
"""
from __future__ import annotations

from .agent_action_proposal_acceptance import AgentActionProposalAcceptanceService
from .agent_action_proposal_feedback import apply_feedback_down_rank, proposal_feedback_decision
from .agent_action_proposal_models import (
    AGENT_ACTION_PROPOSAL_ACCEPT_SCHEMA_VERSION,
    AGENT_ACTION_PROPOSAL_FEEDBACK_POLICY_VERSION,
    AGENT_ACTION_PROPOSAL_MAX_CHARS,
    AGENT_ACTION_PROPOSAL_REVIEW_SCHEMA_VERSION,
    AGENT_ACTION_PROPOSAL_SCHEMA_VERSION,
    AGENT_ACTION_PROPOSAL_THREAD_EVENT_SCHEMA_VERSION,
    AgentActionProposalAcceptRequest,
    AgentActionProposalAcceptResult,
    AgentActionProposalDraft,
    AgentActionProposalFeedbackDecision,
    AgentActionProposalFeedbackSignal,
    AgentActionProposalNotActionable,
    AgentActionProposalNotFound,
    AgentActionProposalRecord,
    AgentActionProposalReviewDecision,
    AgentActionProposalReviewRequest,
    AgentActionProposalReviewResult,
    AgentActionProposalStateError,
    AgentActionProposalStatus,
    AgentActionProposalType,
    AgentActionProposalWrite,
)
from .agent_action_proposal_payloads import (
    _agent_key,
    _proposal_key,
    options_from_accept_request,
    proposal_record_ref,
    proposal_write_from_draft,
    targets_from_accept_request,
)
from .agent_action_proposal_ports import (
    ActionCatalogResolver,
    ActionRequestSubmitter,
    AgentActionProposalStore,
    AgentActionProposalWriter,
    AgentTaskThreadWriter,
)
from .agent_action_proposal_review import AgentActionProposalReviewService
from .agent_action_proposal_writer import AgentActionProposalService

# Legacy private helper aliases kept for compatibility with older imports.
_apply_feedback_down_rank = apply_feedback_down_rank
_targets_from_accept_request = targets_from_accept_request
_options_from_accept_request = options_from_accept_request

__all__ = [
    "AGENT_ACTION_PROPOSAL_ACCEPT_SCHEMA_VERSION",
    "AGENT_ACTION_PROPOSAL_FEEDBACK_POLICY_VERSION",
    "AGENT_ACTION_PROPOSAL_MAX_CHARS",
    "AGENT_ACTION_PROPOSAL_REVIEW_SCHEMA_VERSION",
    "AGENT_ACTION_PROPOSAL_SCHEMA_VERSION",
    "AGENT_ACTION_PROPOSAL_THREAD_EVENT_SCHEMA_VERSION",
    "ActionCatalogResolver",
    "ActionRequestSubmitter",
    "AgentActionProposalAcceptanceService",
    "AgentActionProposalAcceptRequest",
    "AgentActionProposalAcceptResult",
    "AgentActionProposalDraft",
    "AgentActionProposalFeedbackDecision",
    "AgentActionProposalFeedbackSignal",
    "AgentActionProposalNotActionable",
    "AgentActionProposalNotFound",
    "AgentActionProposalRecord",
    "AgentActionProposalReviewDecision",
    "AgentActionProposalReviewRequest",
    "AgentActionProposalReviewResult",
    "AgentActionProposalReviewService",
    "AgentActionProposalService",
    "AgentActionProposalStateError",
    "AgentActionProposalStatus",
    "AgentActionProposalStore",
    "AgentActionProposalType",
    "AgentActionProposalWrite",
    "AgentActionProposalWriter",
    "AgentTaskThreadWriter",
    "_agent_key",
    "_apply_feedback_down_rank",
    "_options_from_accept_request",
    "_proposal_key",
    "_targets_from_accept_request",
    "options_from_accept_request",
    "proposal_feedback_decision",
    "proposal_record_ref",
    "proposal_write_from_draft",
    "targets_from_accept_request",
]
