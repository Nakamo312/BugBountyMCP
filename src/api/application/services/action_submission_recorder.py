"""Persistence/recovery helpers for action submissions."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import UUID

from api.application.contracts import (
    ResolvedActionCommand,
    ActionSubmission,
    EventEnvelope,
    PolicyDecision,
)
from api.application.ports.action import ActionPolicyResultWriter, AllowedActionQueueWriter
from api.application.services.action_errors import ActionSubmissionConflict

SubmissionLookup = Callable[[UUID], Awaitable[ActionSubmission | None]]


class ActionSubmissionRecorder:
    """Record submission state through scenario-specific write ports."""

    def __init__(
        self,
        *,
        policy_results: ActionPolicyResultWriter,
        allowed_actions: AllowedActionQueueWriter,
        submission_lookup: SubmissionLookup,
    ) -> None:
        self.policy_results = policy_results
        self.allowed_actions = allowed_actions
        self.submission_lookup = submission_lookup

    async def record_policy_result_or_recover(
        self,
        action: ResolvedActionCommand,
        decision: PolicyDecision,
    ) -> ActionSubmission | None:
        try:
            await self.policy_results.record_policy_result(action, decision)
        except ActionSubmissionConflict:
            recovered = await self.submission_lookup(action.action_id)
            if recovered is not None:
                return recovered
            raise
        return None

    async def create_allowed_action_or_recover(
        self,
        action: ResolvedActionCommand,
        decision: PolicyDecision,
        envelope: EventEnvelope,
        *,
        scope_id: UUID,
    ) -> ActionSubmission | None:
        try:
            await self.allowed_actions.create_allowed_action(
                action,
                decision,
                envelope,
                scope_id=scope_id,
            )
        except ActionSubmissionConflict:
            recovered = await self.submission_lookup(action.action_id)
            if recovered is not None:
                return recovered
            raise
        return None
