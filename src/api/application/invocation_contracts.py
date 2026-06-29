from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.application.contract_enums import SafetyLevel
from api.application.execution_limits import ExecutionBudget


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
    execution_budget: ExecutionBudget
    safety_level: SafetyLevel
    scope_decision_id: UUID
    policy_decision_id: UUID
    campaign_id: UUID
    correlation_id: UUID
    requested_by: str | None = None
    source_event_id: UUID | None = None
    parent_artifact_id: UUID | None = None
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


class RunnerInvocationContext(BaseModel):
    """Current runner execution context for downstream pipeline events.

    This is deliberately not a ToolInvocation. It identifies the node that is
    currently executing and may carry inherited action ceilings, but it does
    not pretend that a downstream worker is the original capability/profile.
    """

    model_config = ConfigDict(extra="forbid")

    job_id: UUID | None = None
    run_id: UUID | None = None
    program_id: UUID
    node_id: str = Field(..., min_length=1)
    targets: list[str] = Field(default_factory=list)
    options: dict[str, Any] = Field(default_factory=dict)
    execution_budget: ExecutionBudget | None = None
    safety_level: SafetyLevel | None = None
    scope_decision_id: UUID | None = None
    policy_decision_id: UUID | None = None
    campaign_id: UUID | None = None
    correlation_id: UUID | None = None
    requested_by: str | None = None
    source_event_id: UUID | None = None
    parent_artifact_id: UUID | None = None
    root_action_id: UUID | None = None
    root_capability_id: str | None = None
    root_profile_id: str | None = None
    upstream_node_id: str | None = None
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

    def downstream_payload(self) -> dict[str, Any]:
        """Return compact JSON-safe context for a downstream event payload."""
        data = self.model_dump(mode="json", exclude_none=True, exclude={"payload"})
        data["target_count"] = len(self.targets)
        data.pop("targets", None)
        return data


class ToolResult(BaseModel):
    """Normalized result metadata for runner output before ingestion."""

    run_id: UUID
    capability_id: str
    status: str
    result_count: int = 0
    raw_ref: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
