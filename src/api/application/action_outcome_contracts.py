from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from api.application.contract_enums import ActionStatus, ExecutionStatus, TerminalOutcome


class ActionRunResult(BaseModel):
    """Bounded execution summary for one run belonging to an action."""

    run_id: UUID
    job_id: UUID
    status: ExecutionStatus
    terminal_outcome: TerminalOutcome | None = None
    attempt: int = Field(ge=1)
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class ActionOutcomeMeasures(BaseModel):
    """Run-scoped measurements used to remember action utility.

    These counters describe what the action changed or exposed to the system.
    They deliberately do not encode vulnerability classes. Unknown novelty fields
    stay nullable until a projection can measure them without guessing.
    """

    raw_artifact_count: int = Field(default=0, ge=0)
    raw_artifact_bytes: int = Field(default=0, ge=0)
    observed_hosts_count: int = Field(default=0, ge=0)
    observed_services_count: int = Field(default=0, ge=0)
    observed_endpoints_count: int = Field(default=0, ge=0)
    http_observation_count: int = Field(default=0, ge=0)
    javascript_reference_count: int = Field(default=0, ge=0)
    new_hosts_count: int | None = Field(default=None, ge=0)
    new_services_count: int | None = Field(default=None, ge=0)
    new_endpoints_count: int | None = Field(default=None, ge=0)
    new_surface_nodes_count: int | None = Field(default=None, ge=0)
    new_surface_edges_count: int | None = Field(default=None, ge=0)
    new_surface_clusters_count: int | None = Field(default=None, ge=0)
    new_surface_deltas_count: int | None = Field(default=None, ge=0)
    new_graph_facts_count: int | None = Field(default=None, ge=0)
    new_search_documents_count: int | None = Field(default=None, ge=0)
    duration_ms: int | None = Field(default=None, ge=0)
    error_count: int = Field(default=0, ge=0)


class ActionOutcomeScore(BaseModel):
    """Deterministic utility score and explainable components."""

    information_gain_score: float = Field(ge=0.0)
    score_version: str
    score_breakdown: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class ActionOutcomeDraft:
    """Measured run outcome ready for an external scoring policy."""

    row: Mapping[str, Any]
    outcome_id: UUID
    measures: ActionOutcomeMeasures
    status: ExecutionStatus
    terminal_outcome: TerminalOutcome | None


class ActionOutcomeRecord(BaseModel):
    """Persisted memory row for the measured outcome of one run."""

    outcome_id: UUID
    program_id: UUID
    action_id: UUID
    job_id: UUID
    run_id: UUID
    campaign_id: UUID | None = None
    capability_id: str
    profile_id: str
    node_id: str | None = None
    event_name: str | None = None
    correlation_id: UUID | None = None
    status: ExecutionStatus
    terminal_outcome: TerminalOutcome | None = None
    attempt: int = Field(ge=1)
    target_count: int | None = Field(default=None, ge=0)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    error_count: int = Field(default=0, ge=0)
    error_message: str | None = None
    measures: ActionOutcomeMeasures
    score: ActionOutcomeScore
    manual_interest: bool | None = None
    manual_stop: bool | None = None
    continued_by_followup: bool | None = None
    report_created: bool | None = None
    triage_outcome: str | None = None
    created_at: datetime
    updated_at: datetime


class ActionOutcomeFeedback(BaseModel):
    """Human or workflow feedback that updates action outcome memory.

    Feedback stores utility signals about what happened after an action. It is
    intentionally generic: continue, stop, interest, report, and triage result.
    It does not encode vulnerability classes or expert bug rules.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: UUID | None = None
    manual_interest: bool | None = None
    manual_stop: bool | None = None
    continued_by_followup: bool | None = None
    report_created: bool | None = None
    triage_outcome: str | None = Field(default=None, max_length=100)
    actor: str = Field(default="human", min_length=1, max_length=150)
    source: str = Field(default="api", min_length=1, max_length=100)
    reason: str | None = Field(default=None, max_length=2000)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    @field_validator("triage_outcome")
    @classmethod
    def _strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @model_validator(mode="after")
    def _require_feedback_signal(self) -> "ActionOutcomeFeedback":
        if not any(
            value is not None
            for value in (
                self.manual_interest,
                self.manual_stop,
                self.continued_by_followup,
                self.report_created,
                self.triage_outcome,
            )
        ):
            raise ValueError("at least one action outcome feedback signal is required")
        return self


class ActionOutcomeFeedbackRecord(BaseModel):
    """Audited feedback event applied to one action outcome."""

    feedback_id: UUID
    outcome_id: UUID
    program_id: UUID
    action_id: UUID
    job_id: UUID
    run_id: UUID
    campaign_id: UUID | None = None
    manual_interest: bool | None = None
    manual_stop: bool | None = None
    continued_by_followup: bool | None = None
    report_created: bool | None = None
    triage_outcome: str | None = None
    actor: str
    source: str
    reason: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    created_at: datetime
    outcome: ActionOutcomeRecord


class ActionArtifactReference(BaseModel):
    """Artifact metadata exposed without loading or returning artifact content."""

    artifact_id: UUID
    job_id: UUID | None = None
    run_id: UUID | None = None
    artifact_type: str
    storage_uri: str
    sha256: str
    size_bytes: int = Field(ge=0)
    storage_size_bytes: int = Field(default=0, ge=0)
    content_encoding: str = "identity"
    retention_class: str = "program_lifetime"
    created_at: datetime


class ActionResultRecord(BaseModel):
    """Current execution result aggregate for one control-plane action."""

    action_id: UUID
    action_status: ActionStatus
    ready: bool
    runs: list[ActionRunResult] = Field(default_factory=list)
    artifacts: list[ActionArtifactReference] = Field(default_factory=list)
