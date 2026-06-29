"""Persistence/recovery helpers for action submissions."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import UUID

from api.application.contracts import (
    ActionRequest,
    ActionSubmission,
    EventEnvelope,
    PolicyDecision,
)
from api.application.ports.action import ActionCommandPort

SubmissionLookup = Callable[[UUID], Awaitable[ActionSubmission | None]]


class ActionSubmissionRecorder:
    """Record command decisions and recover already-created submissions."""

    def __init__(
        self,
        *,
        commands: ActionCommandPort,
        submission_lookup: SubmissionLookup,
    ) -> None:
        self.commands = commands
        self.submission_lookup = submission_lookup

    async def record_policy_result_or_recover(
        self,
        action: ActionRequest,
        decision: PolicyDecision,
    ) -> ActionSubmission | None:
        try:
            await self.commands.record_policy_result(action, decision)
        except Exception:
            # Idempotency recovery intentionally catches persistence conflicts broadly:
            # duplicate records may surface through different DB/adapter exception types.
            recovered = await self.submission_lookup(action.action_id)
            if recovered is not None:
                return recovered
            raise
        return None

    async def create_allowed_action_or_recover(
        self,
        action: ActionRequest,
        decision: PolicyDecision,
        envelope: EventEnvelope,
        *,
        scope_id: UUID,
    ) -> ActionSubmission | None:
        try:
            await self.commands.create_allowed_action(
                action,
                decision,
                envelope,
                scope_id=scope_id,
            )
        except Exception:
            # Idempotency recovery intentionally catches persistence conflicts broadly:
            # duplicate records may surface through different DB/adapter exception types.
            recovered = await self.submission_lookup(action.action_id)
            if recovered is not None:
                return recovered
            raise
        return None
