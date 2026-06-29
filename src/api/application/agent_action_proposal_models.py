"""Data contracts for agent action proposals."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.application.contracts import ActionSubmission
from api.application.execution_limits import ExecutionBudgetRequest


AGENT_ACTION_PROPOSAL_SCHEMA_VERSION = "agent-action-proposal.v1"
AGENT_ACTION_PROPOSAL_ACCEPT_SCHEMA_VERSION = "agent-action-proposal-accept.v1"
AGENT_ACTION_PROPOSAL_REVIEW_SCHEMA_VERSION = "agent-action-proposal-review.v1"
AGENT_ACTION_PROPOSAL_FEEDBACK_POLICY_VERSION = "agent-action-proposal-feedback-policy.v1"
AGENT_ACTION_PROPOSAL_THREAD_EVENT_SCHEMA_VERSION = "agent-action-proposal-thread-event.v1"
AGENT_ACTION_PROPOSAL_MAX_CHARS = 4_000


class AgentActionProposalStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SUPPRESSED = "suppressed"
    EXPIRED = "expired"


class AgentActionProposalType(str, Enum):
    INVESTIGATION_TASK = "investigation_task"
    TOOL_ACTION = "tool_action"


class AgentActionProposalReviewDecision(str, Enum):
    REJECTED = "rejected"
    SUPPRESSED = "suppressed"


class AgentActionProposalDraft(BaseModel):
    """A proposal emitted by an agent runtime before durable storage."""

    model_config = ConfigDict(extra="forbid")

    proposal_type: AgentActionProposalType = AgentActionProposalType.INVESTIGATION_TASK
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=AGENT_ACTION_PROPOSAL_MAX_CHARS)
    rationale: str = Field(default="", max_length=AGENT_ACTION_PROPOSAL_MAX_CHARS)
    capability_id: str | None = Field(default=None, max_length=100)
    profile_id: str | None = Field(default=None, max_length=100)
    priority: str = Field(default="medium", max_length=30)
    risk_level: str = Field(default="low", max_length=30)
    expected_gain: str = Field(default="", max_length=1000)
    action_intent: str = Field(default="", max_length=1000)
    action_params: dict[str, Any] = Field(default_factory=dict)
    context_refs: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("title", "summary")
    @classmethod
    def required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be blank")
        return stripped

    @field_validator("capability_id", "profile_id", "rationale", "priority", "risk_level", "expected_gain", "action_intent")
    @classmethod
    def optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class AgentActionProposalReviewRequest(BaseModel):
    """Explicit human/scheduler feedback for an agent proposal."""

    model_config = ConfigDict(extra="forbid")

    reviewed_by: str = Field(default="human", min_length=1, max_length=150)
    reason: str | None = Field(default=None, max_length=2000)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    feedback_tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("reviewed_by")
    @classmethod
    def _normalize_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("reviewed_by must not be blank")
        return stripped

    @field_validator("reason")
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("feedback_tags", mode="before")
    @classmethod
    def _normalize_feedback_tags(cls, value: Any) -> list[str]:
        if value is None:
            return []
        candidates = [value] if isinstance(value, str) else list(value)
        normalized: list[str] = []
        seen: set[str] = set()
        for item in candidates:
            tag = str(item).strip().lower().replace(" ", "-")[:60]
            if tag and tag not in seen:
                seen.add(tag)
                normalized.append(tag)
        return normalized[:20]


class AgentActionProposalAcceptRequest(BaseModel):
    """Command to turn a proposal into an ActionRequest."""

    model_config = ConfigDict(extra="forbid")

    accepted_by: str = Field(default="human", min_length=1, max_length=150)
    reason: str | None = Field(default=None, max_length=2000)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    capability_id: str | None = Field(default=None, max_length=100)
    profile_id: str | None = Field(default=None, max_length=100)
    targets: list[str] = Field(default_factory=list)
    options: dict[str, Any] = Field(default_factory=dict)
    budget: ExecutionBudgetRequest | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("accepted_by")
    @classmethod
    def _normalize_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("accepted_by must not be blank")
        return stripped

    @field_validator("capability_id", "profile_id", "reason")
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("targets", mode="before")
    @classmethod
    def _normalize_targets(cls, value: Any) -> list[str]:
        if value is None:
            return []
        candidates = [value] if isinstance(value, str) else list(value)
        return [str(target).strip() for target in candidates if str(target).strip()]


class AgentActionProposalRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: UUID
    program_id: UUID
    campaign_id: UUID | None = None
    task_id: UUID
    source_message_id: UUID
    agent_key: str
    proposal_key: str
    proposal_type: AgentActionProposalType
    status: AgentActionProposalStatus
    title: str
    summary: str
    rationale: str
    capability_id: str | None = None
    profile_id: str | None = None
    priority: str
    risk_level: str
    expected_gain: str
    action_intent: str
    action_params: dict[str, Any] = Field(default_factory=dict)
    context_refs: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    produced_by: str
    accepted_action_id: UUID | None = None
    accepted_by: str | None = None
    accepted_reason: str | None = None
    accepted_at: Any | None = None
    reviewed_by: str | None = None
    review_reason: str | None = None
    review_feedback: dict[str, Any] = Field(default_factory=dict)
    reviewed_at: Any | None = None


class AgentActionProposalAcceptResult(BaseModel):
    """Result of accepting a proposal through the control-plane boundary."""

    model_config = ConfigDict(extra="forbid")

    proposal: AgentActionProposalRecord
    action_submission: ActionSubmission


class AgentActionProposalReviewResult(BaseModel):
    """Result of rejecting or suppressing an agent proposal."""

    model_config = ConfigDict(extra="forbid")

    proposal: AgentActionProposalRecord
    decision: AgentActionProposalReviewDecision


@dataclass(frozen=True, slots=True)
class AgentActionProposalWrite:
    """Sanitized proposal ready for storage."""

    proposal_id: UUID
    program_id: UUID
    campaign_id: UUID | None
    task_id: UUID
    source_message_id: UUID
    agent_key: str
    proposal_key: str
    draft: AgentActionProposalDraft
    title: str
    summary: str
    rationale: str
    context_refs: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AgentActionProposalFeedbackSignal:
    """Negative review signal from previous agent proposals."""

    proposal_id: UUID
    campaign_id: UUID | None
    agent_key: str
    proposal_type: AgentActionProposalType
    feedback_type: AgentActionProposalReviewDecision
    confidence: float
    title: str
    capability_id: str | None = None
    profile_id: str | None = None
    action_intent: str | None = None
    context_refs: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    feedback_tags: tuple[str, ...] = field(default_factory=tuple)
    reason: str | None = None
    created_at: Any | None = None


@dataclass(frozen=True, slots=True)
class AgentActionProposalFeedbackDecision:
    """Decision made before storing a newly generated proposal draft."""

    action: str
    match_score: float = 0.0
    signal: AgentActionProposalFeedbackSignal | None = None

    @property
    def is_suppressed(self) -> bool:
        return self.action == "suppress"

    @property
    def is_down_ranked(self) -> bool:
        return self.action == "down_rank"


class AgentActionProposalNotFound(Exception):
    """Raised when an accept/review command targets no stored proposal."""


class AgentActionProposalStateError(Exception):
    """Raised when a proposal cannot transition from its current state."""


class AgentActionProposalNotActionable(Exception):
    """Raised when a proposal lacks enough explicit data for ActionService."""
