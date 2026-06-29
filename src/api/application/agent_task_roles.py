"""Compatibility exports for role-specific agent task replies."""
from __future__ import annotations

from api.application.agent_task_role_composer import AgentTaskRoleComposer
from api.application.agent_task_role_context import (
    ContextRefSummary,
    _bounded_context_dicts,
    _dedupe_ref_tuple,
    _outcome_metadata,
    _proposal_metadata,
    _ref_kind,
    _safe_ref,
    _safe_short,
    _safe_value,
)
from api.application.agent_task_role_models import AgentTaskRoleReply
from api.application.agent_task_role_proposals import (
    _proposal_context_refs,
    _proposal_draft,
    _role_metadata,
)
from api.application.agent_task_role_text import (
    _artifact_focus,
    _artifact_next_step,
    _artifact_proposal_title,
    _coordinator_expected_gain,
    _coordinator_next_step,
    _coordinator_priority,
    _coordinator_proposal_title,
    _critic_next_step,
    _critic_proposal_title,
    _critic_risk_brief,
    _has_stop_signal,
    _has_surface_signal,
    _human_feedback_flag,
    _join_sections,
    _nonzero_count_line,
    _pending_proposal_brief,
    _recent_http_brief,
    _recent_javascript_brief,
    _recent_outcome_brief,
    _report_readiness_brief,
    _request_line,
    _surface_focus,
    _surface_next_step,
    _surface_proposal_title,
    normalize_agent_role,
)

__all__ = [
    "AgentTaskRoleComposer",
    "AgentTaskRoleReply",
    "ContextRefSummary",
    "normalize_agent_role",
]
