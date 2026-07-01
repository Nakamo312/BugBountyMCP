from __future__ import annotations

from uuid import uuid4

import pytest

from api.application.agent_task_budget import (
    AgentTaskBudgetMode,
    AgentTaskRuntimeBudgetPolicy,
    BudgetedAgentTaskRuntime,
)
from api.application.agent.task.inbox import (
    AgentTaskRuntimeRequest,
    AgentTaskRuntimeResult,
)
from api.application.agent_tasks import AgentTaskMessageKind, AgentTaskStatus


class RecordingRuntime:
    def __init__(self, *, body: str = "runtime reply") -> None:
        self.calls: list[AgentTaskRuntimeRequest] = []
        self.body = body

    async def handle(self, request: AgentTaskRuntimeRequest) -> AgentTaskRuntimeResult:
        self.calls.append(request)
        return AgentTaskRuntimeResult(
            agent_key="coordinator",
            body=self.body,
            message_kind=AgentTaskMessageKind.NOTE,
            status=AgentTaskStatus.WAITING,
            metadata={"runtime": "recording"},
        )


def _request(**metadata) -> AgentTaskRuntimeRequest:
    return AgentTaskRuntimeRequest(
        task_id=uuid4(),
        message_id=uuid4(),
        program_id=uuid4(),
        campaign_id=uuid4(),
        correlation_id=uuid4(),
        target_agent="coordinator",
        schema_version="agent-task-prompt.v1",
        body_excerpt="x" * 10_000,
        body_hash="a" * 64,
        context_refs=tuple({"idx": idx} for idx in range(100)),
        metadata=metadata,
        source="ui",
    )


def test_budget_policy_defaults_to_no_model_mode_and_trims_context() -> None:
    policy = AgentTaskRuntimeBudgetPolicy(default_mode="none")

    decision = policy.evaluate(_request())

    assert decision.selected_mode is AgentTaskBudgetMode.NONE
    assert decision.runtime_allowed is False
    assert decision.limits.llm_allowed is False
    assert decision.prompt_chars_after == 1500
    assert decision.context_refs_after == 8
    assert decision.reason_code == "model_usage_disabled"


def test_budget_policy_downgrades_deep_when_globally_disabled() -> None:
    policy = AgentTaskRuntimeBudgetPolicy(default_mode="cheap", allow_deep=False)

    decision = policy.evaluate(_request(budget_mode="deep", deep_mode_confirmed=True))

    assert decision.requested_mode is AgentTaskBudgetMode.DEEP
    assert decision.selected_mode is AgentTaskBudgetMode.NORMAL
    assert decision.runtime_allowed is True
    assert decision.limits.deep_mode is False
    assert decision.reason_code.endswith("with_truncation")
    assert "deep_mode_disabled" in decision.reason_code
    assert decision.deep_approval is not None
    assert decision.deep_approval.approved is False
    assert decision.as_metadata()["deep_approval"]["globally_allowed"] is False


def test_budget_policy_requires_explicit_deep_confirmation() -> None:
    policy = AgentTaskRuntimeBudgetPolicy(default_mode="cheap", allow_deep=True)

    decision = policy.evaluate(_request(budget_mode="deep", created_by="human"))

    assert decision.requested_mode is AgentTaskBudgetMode.DEEP
    assert decision.selected_mode is AgentTaskBudgetMode.NORMAL
    assert "deep_mode_requires_explicit_confirmation" in decision.reason_code
    assert decision.as_metadata()["deep_approval"]["confirmation_provided"] is False


def test_budget_policy_allows_deep_with_confirmation_and_actor() -> None:
    policy = AgentTaskRuntimeBudgetPolicy(
        default_mode="cheap",
        allow_deep=True,
        deep_allowed_actors="operator,admin",
    )

    decision = policy.evaluate(
        _request(
            budget_mode="deep",
            deep_mode_confirmed=True,
            created_by="operator",
        )
    )

    assert decision.requested_mode is AgentTaskBudgetMode.DEEP
    assert decision.selected_mode is AgentTaskBudgetMode.DEEP
    assert decision.runtime_allowed is True
    assert decision.limits.deep_mode is True
    assert decision.reason_code.endswith("with_truncation")
    assert "deep_mode_approved" in decision.reason_code
    assert decision.as_metadata()["deep_approval"]["actor"] == "operator"
    assert decision.as_metadata()["deep_approval"]["approved"] is True


def test_budget_policy_downgrades_deep_for_disallowed_actor() -> None:
    policy = AgentTaskRuntimeBudgetPolicy(
        default_mode="cheap",
        allow_deep=True,
        deep_allowed_actors="operator,admin",
    )

    decision = policy.evaluate(
        _request(
            budget_mode="deep",
            deep_mode_confirmed=True,
            created_by="human",
        )
    )

    assert decision.selected_mode is AgentTaskBudgetMode.NORMAL
    assert "deep_mode_actor_not_allowed" in decision.reason_code
    assert decision.as_metadata()["deep_approval"]["actor_allowed"] is False


@pytest.mark.asyncio
async def test_budgeted_runtime_uses_fallback_when_model_usage_disabled() -> None:
    inner = RecordingRuntime(body="inner")
    fallback = RecordingRuntime(body="fallback")
    runtime = BudgetedAgentTaskRuntime(
        inner=inner,
        fallback=fallback,
        policy=AgentTaskRuntimeBudgetPolicy(default_mode="none"),
    )

    result = await runtime.handle(_request())

    assert not inner.calls
    assert len(fallback.calls) == 1
    assert len(fallback.calls[0].context_refs) == 8
    assert len(fallback.calls[0].body_excerpt) == 1500
    assert result.body == "fallback"
    assert result.metadata["budget"]["selected_mode"] == "none"
    assert result.metadata["budget"]["llm_allowed"] is False


@pytest.mark.asyncio
async def test_budgeted_runtime_uses_inner_for_allowed_mode_and_caps_output() -> None:
    inner = RecordingRuntime(body="y" * 10_000)
    fallback = RecordingRuntime(body="fallback")
    runtime = BudgetedAgentTaskRuntime(
        inner=inner,
        fallback=fallback,
        policy=AgentTaskRuntimeBudgetPolicy(default_mode="cheap"),
    )

    result = await runtime.handle(_request())

    assert len(inner.calls) == 1
    assert not fallback.calls
    assert len(inner.calls[0].context_refs) == 12
    assert len(inner.calls[0].body_excerpt) == 2000
    assert len(result.body) == 1500
    assert result.metadata["budget"]["selected_mode"] == "cheap"
    assert result.metadata["budget"]["llm_allowed"] is True
