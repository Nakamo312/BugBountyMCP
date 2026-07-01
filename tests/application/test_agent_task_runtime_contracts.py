from __future__ import annotations

import importlib
from uuid import uuid4

import pytest

from api.application.agent_task_runtime_contracts import (
    AgentTaskRuntimeRequest,
    BoundedAgentTaskRuntime,
)
from api.application.agent_tasks import AGENT_TASK_PROMPT_SCHEMA_VERSION, AgentTaskMessageKind


def _request() -> AgentTaskRuntimeRequest:
    return AgentTaskRuntimeRequest(
        task_id=uuid4(),
        message_id=uuid4(),
        program_id=uuid4(),
        campaign_id=None,
        correlation_id=None,
        target_agent="Surface Agent",
        schema_version=AGENT_TASK_PROMPT_SCHEMA_VERSION,
        body_excerpt="review surface refs",
        body_hash=None,
    )


def test_runtime_contracts_import_without_legacy_processor_cycle() -> None:
    contracts = importlib.import_module("api.application.agent_task_runtime_contracts")
    processor = importlib.import_module("api.application.agent.task.inbox.processor")
    bridge = importlib.import_module("api.application.agent.task.inbox")

    assert contracts.AgentTaskRuntimeRequest is bridge.AgentTaskRuntimeRequest
    assert processor.AgentTaskInboxProcessor is bridge.AgentTaskInboxProcessor


@pytest.mark.asyncio
async def test_bounded_runtime_stays_deterministic_and_pointer_only() -> None:
    result = await BoundedAgentTaskRuntime().handle(_request())

    assert result.agent_key == "surface-agent"
    assert result.message_kind is AgentTaskMessageKind.QUESTION
    assert result.metadata["runtime"] == "bounded-agent-task-runtime.v1"
    assert result.metadata["boundary"]["tool_execution"] == "forbidden_from_agent_task_runtime"
