"""Acceptance bridge for internal action-experience proposals.

Action-experience proposals are produced by the graph-projector/GDS memory loop.
They are advisory ranking artifacts, not execution commands. This module defines
an explicit boundary for turning a pending proposal into a normal ActionRequest.
The bridge never runs tools directly: it submits through ActionService so catalog
resolution, scope, policy, approval and budget checks remain the only execution
path.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.application.contracts import ActionRequest, ActionSubmission
from api.application.execution_limits import ExecutionBudgetRequest
from api.application.research.sanitizer import sanitize_json


ACTION_EXPERIENCE_PROPOSAL_ACCEPT_SCHEMA_VERSION = "action-experience-proposal-accept.v1"
ACTION_EXPERIENCE_PROPOSAL_REVIEW_SCHEMA_VERSION = "action-experience-proposal-review.v1"


class ActionExperienceProposalStatus(str, Enum):
    PENDING = "pending"
    ACCEPTING = "accepting"
    ACCEPTED = "accepted"
    ACCEPT_FAILED = "accept_failed"
    REJECTED = "rejected"
    SUPPRESSED = "suppressed"
    EXPIRED = "expired"


class ActionExperienceProposalNotFound(LookupError):
    """Raised when a requested action-experience proposal does not exist."""


class ActionExperienceProposalStateError(RuntimeError):
    """Raised when a proposal cannot transition from its current state."""


class ActionExperienceProposalNotActionable(ValueError):
    """Raised when a proposal lacks enough explicit input to create an action."""


class ActionExperienceProposalAcceptRequest(BaseModel):
    """Explicit command to convert an advisory experience proposal to an action.

    Targets are required on purpose. GDS proposals rank capability/profile pairs
    over a structural context, but they must not guess execution targets. The
    operator/scheduler has to provide the concrete targets before ActionService
    can validate scope and policy.
    """

    model_config = ConfigDict(extra="forbid")

    accepted_by: str = Field(default="human", min_length=1, max_length=150)
    reason: str | None = Field(default=None, max_length=2000)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    targets: list[str] = Field(default_factory=list)
    options: dict[str, Any] = Field(default_factory=dict)
    budget: ExecutionBudgetRequest | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("accepted_by")
    @classmethod
    def _normalize_actor(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("accepted_by must not be blank")
        return stripped

    @field_validator("reason")
    @classmethod
    def _normalize_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("targets", mode="before")
    @classmethod
    def _normalize_targets(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            candidates = [value]
        else:
            candidates = list(value)
        return [str(target).strip() for target in candidates if str(target).strip()]




class ActionExperienceProposalReviewDecision(str, Enum):
    REJECTED = "rejected"
    SUPPRESSED = "suppressed"


class ActionExperienceProposalReviewRequest(BaseModel):
    """Operator feedback on an advisory experience proposal.

    Review feedback changes only the proposal state. It never submits an action
    and never rewrites the source ActionOutcome. Rejected/suppressed proposals
    are later consumed by the review-prior ranking layer.
    """

    model_config = ConfigDict(extra="forbid")

    reviewed_by: str = Field(default="human", min_length=1, max_length=150)
    reason: str | None = Field(default=None, max_length=2000)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("reviewed_by")
    @classmethod
    def _normalize_actor(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("reviewed_by must not be blank")
        return stripped

    @field_validator("reason")
    @classmethod
    def _normalize_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class ActionExperienceProposalRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: UUID
    proposal_run_id: UUID
    program_id: UUID
    campaign_id: UUID | None = None
    source_outcome_id: UUID
    source_action_id: UUID
    source_job_id: UUID
    source_run_id: UUID
    proposal_key: str
    status: ActionExperienceProposalStatus
    rank: int
    capability_id: str
    profile_id: str
    utility_score: float
    sample_count: int
    avg_similarity: float
    avg_information_gain_score: float
    human_positive_rate: float
    human_stop_rate: float
    explanation: dict[str, Any] = Field(default_factory=dict)
    produced_by: str
    created_at: Any | None = None
    updated_at: Any | None = None


class ActionExperienceProposalAcceptResult(BaseModel):
    """Result of accepting an advisory experience proposal through ActionService."""

    model_config = ConfigDict(extra="forbid")

    proposal: ActionExperienceProposalRecord
    action_submission: ActionSubmission


class ActionExperienceProposalReviewResult(BaseModel):
    """Result of rejecting or suppressing an advisory experience proposal."""

    model_config = ConfigDict(extra="forbid")

    proposal: ActionExperienceProposalRecord
    boundary: dict[str, bool]


class ActionExperienceProposalStore(Protocol):
    async def get_proposal(self, proposal_id: UUID) -> ActionExperienceProposalRecord | None: ...

    async def claim_acceptance(
        self,
        *,
        proposal_id: UUID,
        action_id: UUID,
        accepted_by: str,
        reason: str | None,
        confidence: float,
        metadata: dict[str, Any],
    ) -> ActionExperienceProposalRecord | None: ...

    async def retry_acceptance(
        self,
        *,
        proposal_id: UUID,
        action_id: UUID,
        accepted_by: str,
        reason: str | None,
        confidence: float,
        metadata: dict[str, Any],
    ) -> ActionExperienceProposalRecord | None: ...

    async def mark_accepted(
        self,
        *,
        proposal_id: UUID,
        action_id: UUID,
        accepted_by: str,
        reason: str | None,
        confidence: float,
        metadata: dict[str, Any],
    ) -> ActionExperienceProposalRecord | None: ...

    async def mark_accept_failed(
        self,
        *,
        proposal_id: UUID,
        action_id: UUID,
        accepted_by: str,
        reason: str | None,
        confidence: float,
        metadata: dict[str, Any],
        error: str,
    ) -> ActionExperienceProposalRecord | None: ...

    async def mark_reviewed(
        self,
        *,
        proposal_id: UUID,
        status: ActionExperienceProposalReviewDecision,
        reviewed_by: str,
        reason: str | None,
        confidence: float,
        metadata: dict[str, Any],
    ) -> ActionExperienceProposalRecord | None: ...


class ActionRequestSubmitter(Protocol):
    async def request_action(
        self,
        action: ActionRequest,
        *,
        confidence: float = 0.5,
    ) -> ActionSubmission: ...

    async def get_action_submission(self, action_id: UUID) -> ActionSubmission | None: ...


class ActionCatalogResolver(Protocol):
    async def find_detail(self, *, capability: str, profile: str): ...


class ActionExperienceProposalReviewService:
    """Record operator feedback on advisory proposals without submitting actions."""

    def __init__(self, *, store: ActionExperienceProposalStore) -> None:
        self.store = store

    async def review(
        self,
        *,
        proposal_id: UUID,
        decision: ActionExperienceProposalReviewDecision,
        request: ActionExperienceProposalReviewRequest,
    ) -> ActionExperienceProposalReviewResult:
        proposal = await self.store.get_proposal(proposal_id)
        if proposal is None:
            raise ActionExperienceProposalNotFound(f"Action experience proposal not found: {proposal_id}")
        if proposal.status is not ActionExperienceProposalStatus.PENDING:
            raise ActionExperienceProposalStateError(
                f"Action experience proposal {proposal_id} is not pending: {proposal.status.value}"
            )
        metadata = sanitize_json(
            {
                **request.metadata,
                "schema_version": ACTION_EXPERIENCE_PROPOSAL_REVIEW_SCHEMA_VERSION,
                "source": "action_experience_proposal_review",
                "action_experience_proposal": {
                    "proposal_id": str(proposal.proposal_id),
                    "proposal_run_id": str(proposal.proposal_run_id),
                    "source_outcome_id": str(proposal.source_outcome_id),
                    "source_action_id": str(proposal.source_action_id),
                    "source_job_id": str(proposal.source_job_id),
                    "source_run_id": str(proposal.source_run_id),
                    "proposal_key": proposal.proposal_key,
                    "capability_id": proposal.capability_id,
                    "profile_id": proposal.profile_id,
                    "rank": proposal.rank,
                    "utility_score": proposal.utility_score,
                    "sample_count": proposal.sample_count,
                    "produced_by": proposal.produced_by,
                },
                "review": {
                    "status": decision.value,
                    "reviewed_by": request.reviewed_by,
                    "reason": request.reason,
                    "confidence": request.confidence,
                    "boundary": {
                        "proposal_direct_execution": False,
                        "submitted_through_action_service": False,
                        "source_outcome_rewritten": False,
                        "consumed_by_review_priors": True,
                    },
                },
            }
        )
        reviewed = await self.store.mark_reviewed(
            proposal_id=proposal.proposal_id,
            status=decision,
            reviewed_by=request.reviewed_by,
            reason=request.reason,
            confidence=request.confidence,
            metadata=metadata,
        )
        if reviewed is None:
            raise ActionExperienceProposalStateError(
                f"Action experience proposal {proposal.proposal_id} could not be marked {decision.value}"
            )
        return ActionExperienceProposalReviewResult(
            proposal=reviewed,
            boundary={
                "proposal_direct_execution": False,
                "submitted_through_action_service": False,
                "source_outcome_rewritten": False,
                "consumed_by_review_priors": True,
            },
        )


def __getattr__(name: str):
    if name == "ActionExperienceProposalAcceptanceService":
        from .action_experience_acceptance import ActionExperienceProposalAcceptanceService

        return ActionExperienceProposalAcceptanceService
    raise AttributeError(name)
