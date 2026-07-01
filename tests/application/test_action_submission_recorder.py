from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from api.application.contracts import (
    ActionStatus,
    ActionSubmission,
    PolicyDecision,
    PolicyDecisionStatus,
)
from api.application.services.action_submission_recorder import ActionSubmissionRecorder


def _submission(action_id) -> ActionSubmission:
    return ActionSubmission(
        action_id=action_id,
        status=ActionStatus.QUEUED,
        message="existing action",
        policy_decision=PolicyDecision(
            action_id=action_id,
            status=PolicyDecisionStatus.ALLOWED,
        ),
    )


class _FailingCommands:
    async def record_policy_result(self, action, decision):
        raise RuntimeError("database unavailable")

    async def create_allowed_action(self, action, decision, envelope, *, scope_id):
        raise RuntimeError("database unavailable")


@pytest.mark.asyncio
async def test_recorder_does_not_recover_non_idempotency_failures() -> None:
    action = SimpleNamespace(action_id=uuid4())

    async def lookup_submission(action_id):
        return _submission(action_id)

    failing = _FailingCommands()
    recorder = ActionSubmissionRecorder(
        policy_results=failing,
        allowed_actions=failing,
        submission_lookup=lookup_submission,
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        await recorder.record_policy_result_or_recover(
            action,
            PolicyDecision(action_id=action.action_id, status=PolicyDecisionStatus.ALLOWED),
        )
