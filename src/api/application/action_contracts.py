from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator

from api.application.contract_enums import (
    ActionKind,
    ActionStatus,
    PolicyDecisionStatus,
    SafetyLevel,
)
from api.application.execution_limits import ExecutionBudget, ExecutionBudgetRequest


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
    budget: ExecutionBudgetRequest | None = None
    requested_by: str = "api"
    workflow_id: UUID | None = None
    campaign_id: UUID = Field(default_factory=uuid4)
    correlation_id: UUID = Field(default_factory=uuid4)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    _profile: ScanProfile | None = PrivateAttr(default=None)
    _effective_budget: ExecutionBudget | None = PrivateAttr(default=None)

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

    @property
    def effective_budget(self) -> ExecutionBudget:
        if self._effective_budget is None:
            raise RuntimeError("ActionRequest execution budget has not been resolved")
        return self._effective_budget

    def bind_profile(
        self,
        *,
        capability_id: str,
        profile_id: str,
        options: dict[str, Any] | None = None,
        execution_budget: ExecutionBudget | None = None,
    ) -> "ActionRequest":
        if options is not None:
            self.options = dict(options)
        self._profile = ScanProfile(
            capability_id=capability_id,
            profile_id=profile_id,
            targets=self.targets,
            options=self.options,
        )
        if execution_budget is not None:
            self._effective_budget = execution_budget
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


class ActionEventRecord(BaseModel):
    """Stored event emitted for one control-plane action."""

    event_id: UUID
    action_id: UUID | None = None
    event_type: str
    program_id: UUID
    job_id: UUID | None = None
    run_id: UUID | None = None
    correlation_id: UUID
    causation_id: UUID | None = None
    source: str
    profile: str | None = None
    confidence: float
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
