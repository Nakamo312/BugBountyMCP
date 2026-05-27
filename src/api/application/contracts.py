"""Typed application contracts used across orchestration and MCP boundaries."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


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


class ScanProfile(BaseModel):
    """Validated scan profile request. Runner adapters must only use allowed options."""

    capability_id: str
    profile_id: str
    targets: list[str] = Field(min_length=1)
    options: dict[str, Any] = Field(default_factory=dict)


class ActionRequest(BaseModel):
    """Control-plane request for an action before policy and orchestration."""

    action_id: UUID = Field(default_factory=uuid4)
    kind: ActionKind = ActionKind.SCAN
    program_id: UUID
    profile: ScanProfile
    requested_by: str = "api"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PolicyDecision(BaseModel):
    """Result of checking scope, rate, approval, and capability policy."""

    decision_id: UUID = Field(default_factory=uuid4)
    action_id: UUID
    status: PolicyDecisionStatus
    reasons: list[str] = Field(default_factory=list)
    allowed_targets: list[str] = Field(default_factory=list)
    blocked_targets: list[str] = Field(default_factory=list)


class ActionSubmission(BaseModel):
    """Result returned to the control plane after policy and enqueue decisions."""

    action_id: UUID
    status: ActionStatus
    message: str
    job_id: UUID | None = None
    run_id: UUID | None = None
    event_id: UUID | None = None
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


class ToolResult(BaseModel):
    """Normalized result metadata for runner output before ingestion."""

    run_id: UUID
    capability_id: str
    status: str
    result_count: int = 0
    raw_ref: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class IngestContext:
    """Run and artifact identity supplied to result ingestors."""

    job_id: UUID | None = None
    run_id: UUID | None = None
    correlation_id: UUID | None = None
    raw_artifact_id: UUID | None = None
