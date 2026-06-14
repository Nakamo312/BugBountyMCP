"""Typed application contracts used across orchestration and MCP boundaries."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator


class ActionKind(str, Enum):
    SCAN = "scan"
    ANALYSIS = "analysis"
    TRIAGE = "triage"


class PolicyDecisionStatus(str, Enum):
    ALLOWED = "allowed"
    BLOCKED = "blocked"
    REQUIRES_APPROVAL = "requires_approval"
    REJECTED = "rejected"


class ActionStatus(str, Enum):
    QUEUED = "queued"
    BLOCKED = "blocked"
    REQUIRES_APPROVAL = "requires_approval"
    REJECTED = "rejected"


class ExecutionStatus(str, Enum):
    QUEUED = "queued"
    LEASED = "leased"
    RUNNING = "running"
    FLUSHING = "flushing"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD = "dead"
    CANCELLED = "cancelled"


class ExecutionMode(str, Enum):
    INLINE = "inline"
    SCHEDULED = "scheduled"


class TerminalOutcome(str, Enum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    TOOL_FAILED = "tool_failed"
    SKIPPED = "skipped"
    POLICY_BLOCKED = "policy_blocked"


class SafetyLevel(str, Enum):
    PASSIVE = "passive"
    SAFE_ACTIVE = "safe_active"
    ACTIVE = "active"
    SENSITIVE = "sensitive"


class EventEnvelope(BaseModel):
    """Stable event envelope for RabbitMQ and future event-store replay."""

    model_config = ConfigDict(extra="allow")

    event_id: UUID = Field(default_factory=uuid4)
    event: str = Field(..., min_length=1)
    program_id: UUID
    targets: list[str] = Field(default_factory=list)
    source: str = "unknown"
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    job_id: UUID = Field(default_factory=uuid4)
    run_id: UUID = Field(default_factory=uuid4)
    correlation_id: UUID = Field(default_factory=uuid4)
    causation_id: UUID | None = None
    profile: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("targets")
    @classmethod
    def targets_must_be_strings(cls, value: list[str]) -> list[str]:
        return [target for target in value if isinstance(target, str) and target.strip()]

    @classmethod
    def from_legacy(cls, event: dict[str, Any]) -> "EventEnvelope":
        """Normalize the current loose event dict into a typed envelope."""
        payload = dict(event)
        known = {
            "event",
            "program_id",
            "targets",
            "source",
            "confidence",
            "job_id",
            "run_id",
            "correlation_id",
            "causation_id",
            "profile",
            "payload",
            "created_at",
            "event_id",
        }
        extra_payload = {key: payload.pop(key) for key in list(payload) if key not in known}
        if "target" in extra_payload and "targets" not in event:
            payload["targets"] = [extra_payload["target"]]
        payload["payload"] = {**extra_payload, **payload.get("payload", {})}
        return cls(**payload)

    def to_legacy_dict(self) -> dict[str, Any]:
        """Return a dict compatible with existing consumers during migration."""
        data = self.model_dump(mode="json")
        data["target"] = self.targets[0] if self.targets else None
        data.update(self.payload)
        return data


@dataclass(frozen=True)
class EventDispatchRecord:
    """Leased delivery work for one stored event and one destination."""

    dispatch_id: UUID
    event_id: UUID
    destination: str
    routing_key: str
    attempts: int
    envelope: EventEnvelope


class ScanProfile(BaseModel):
    """Validated scan profile request. Runner adapters must only use allowed options."""

    capability_id: str
    profile_id: str
    targets: list[str] = Field(min_length=1)
    options: dict[str, Any] = Field(default_factory=dict)


class ActionRequest(BaseModel):
    """Public action request selected by active catalog entry."""

    model_config = ConfigDict(extra="forbid")

    action_id: UUID = Field(default_factory=uuid4)
    kind: ActionKind = ActionKind.SCAN
    program_id: UUID
    catalog_id: UUID
    targets: list[str] = Field(min_length=1)
    options: dict[str, Any] = Field(default_factory=dict)
    requested_by: str = "api"
    workflow_id: UUID | None = None
    campaign_id: UUID = Field(default_factory=uuid4)
    correlation_id: UUID = Field(default_factory=uuid4)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    _profile: ScanProfile | None = PrivateAttr(default=None)

    @field_validator("targets", mode="before")
    @classmethod
    def normalize_targets(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            candidates = [value]
        else:
            candidates = list(value)
        return [str(target).strip() for target in candidates if str(target).strip()]

    @property
    def profile(self) -> ScanProfile:
        if self._profile is None:
            raise RuntimeError("ActionRequest catalog entry has not been resolved")
        return self._profile

    def bind_profile(self, *, capability_id: str, profile_id: str) -> "ActionRequest":
        self._profile = ScanProfile(
            capability_id=capability_id,
            profile_id=profile_id,
            targets=self.targets,
            options=self.options,
        )
        return self


class PolicyDecision(BaseModel):
    """Result of checking scope, rate, approval, and capability policy."""

    decision_id: UUID = Field(default_factory=uuid4)
    action_id: UUID
    status: PolicyDecisionStatus
    reasons: list[str] = Field(default_factory=list)
    allowed_targets: list[str] = Field(default_factory=list)
    blocked_targets: list[str] = Field(default_factory=list)
    safety_level: SafetyLevel | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ActionSubmission(BaseModel):
    """Result returned to the control plane after policy and enqueue decisions."""

    action_id: UUID
    status: ActionStatus
    message: str
    job_id: UUID | None = None
    run_id: UUID | None = None
    event_id: UUID | None = None
    campaign_id: UUID | None = None
    correlation_id: UUID | None = None
    workflow_id: UUID | None = None
    wait_url: str | None = None
    events_url: str | None = None
    result_url: str | None = None
    policy_decision: PolicyDecision


class ActionRecord(BaseModel):
    """Stored control-plane action summary for review and approval queues."""

    action_id: UUID
    program_id: UUID
    kind: ActionKind
    capability_id: str
    profile_id: str
    requested_by: str
    status: ActionStatus
    targets: list[str] = Field(default_factory=list)
    options: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class ToolInvocation(BaseModel):
    """Complete typed payload passed from the execution core to a runner."""

    action_id: UUID
    job_id: UUID
    run_id: UUID
    program_id: UUID
    capability_id: str
    profile_id: str
    targets: list[str] = Field(min_length=1)
    options: dict[str, Any] = Field(default_factory=dict)
    safety_level: SafetyLevel
    scope_decision_id: UUID
    policy_decision_id: UUID
    campaign_id: UUID
    correlation_id: UUID
    requested_by: str | None = None
    source_event_id: UUID | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("targets", mode="before")
    @classmethod
    def normalize_targets(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            candidates = [value]
        else:
            candidates = list(value)
        return [str(target).strip() for target in candidates if str(target).strip()]


class ToolResult(BaseModel):
    """Normalized result metadata for runner output before ingestion."""

    run_id: UUID
    capability_id: str
    status: str
    result_count: int = 0
    raw_ref: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class NodeRunClaim:
    """Durable ownership claim for one pipeline node handling one trigger."""

    run_id: UUID
    claim_key: str
    status: ExecutionStatus
    terminal_outcome: TerminalOutcome | None = None

    @property
    def is_terminal(self) -> bool:
        return self.terminal_outcome in {
            TerminalOutcome.COMPLETED,
            TerminalOutcome.PARTIAL,
            TerminalOutcome.TOOL_FAILED,
            TerminalOutcome.SKIPPED,
            TerminalOutcome.POLICY_BLOCKED,
        }


@dataclass(frozen=True)
class ScheduledNodeRun:
    """Leased scheduled node run plus reconstructed input event."""

    run_id: UUID
    node_id: str
    event: dict[str, Any]


@dataclass(frozen=True)
class IngestContext:
    """Run and artifact identity supplied to result ingestors."""

    job_id: UUID | None = None
    run_id: UUID | None = None
    correlation_id: UUID | None = None
    raw_artifact_id: UUID | None = None
