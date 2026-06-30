"""Narrow ports used by ActionService."""
from __future__ import annotations

from typing import Protocol
from uuid import UUID

from api.application.contracts import (
    ActionArtifactReference,
    ActionEventRecord,
    ActionOutcomeFeedback,
    ActionOutcomeFeedbackRecord,
    ActionRecord,
    ActionRequest,
    ResolvedActionCommand,
    ActionRunResult,
    EventEnvelope,
    PolicyDecision,
)
from api.domain.models import ScopeRuleModel


class ScopeRuleProvider(Protocol):
    async def find_by_program(self, program_id: UUID) -> list[ScopeRuleModel]:
        ...


class ActionOutcomeFeedbackWriter(Protocol):
    async def apply_feedback(
        self,
        *,
        action_id: UUID,
        feedback: ActionOutcomeFeedback,
    ) -> ActionOutcomeFeedbackRecord | None:
        ...


class ActionCommandPort(Protocol):
    async def record_policy_result(
        self,
        action: ResolvedActionCommand,
        decision: PolicyDecision,
    ) -> UUID:
        ...

    async def create_allowed_action(
        self,
        action: ResolvedActionCommand,
        decision: PolicyDecision,
        envelope: EventEnvelope,
        *,
        scope_id: UUID,
    ) -> None:
        ...


class ActionQueryPort(Protocol):
    async def list_actions(
        self,
        *,
        status: str | None = None,
        program_id: UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ActionRecord]:
        ...

    async def get_action(self, action_id: UUID) -> ActionRecord | None:
        ...

    async def list_action_events(
        self,
        action_id: UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ActionEventRecord]:
        ...


class ActionResultPort(Protocol):
    async def list_action_runs(self, action_id: UUID) -> list[ActionRunResult]:
        ...

    async def list_action_artifacts(self, action_id: UUID) -> list[ActionArtifactReference]:
        ...


class ActionApprovalPort(Protocol):
    async def get_action_for_approval(self, action_id: UUID):
        ...

    async def get_scope_id(self, action_id: UUID) -> UUID | None:
        ...

    async def approve_and_create_queued_job(
        self,
        action: ResolvedActionCommand,
        decision: PolicyDecision,
        envelope: EventEnvelope,
    ) -> bool:
        ...

    async def reject_action(
        self,
        action: ResolvedActionCommand,
        decision: PolicyDecision,
    ) -> bool:
        ...
