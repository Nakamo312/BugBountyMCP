from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path("services/agent-worker").resolve()))

from api.application.agent.task.inbox import AgentTaskRuntimeResult
from api.application.agent_tasks import (
    AGENT_TASK_PROMPT_MESSAGE_TYPE,
    AGENT_TASK_PROMPT_SCHEMA_VERSION,
    AgentTaskMessageKind,
    AgentTaskStatus,
)
from agent_worker.worker import LangGraphAgentTaskWorker


class RecordingClient:
    def __init__(self, messages) -> None:
        self.messages = messages
        self.claims = []
        self.ingested = []

    async def claim_agent_task_messages(self, **kwargs):
        self.claims.append(kwargs)
        return list(self.messages)

    async def ingest_runtime_result(self, payload):
        self.ingested.append(payload)
        return {"ok": True}


class RecordingRuntime:
    def __init__(self) -> None:
        self.requests = []

    async def handle(self, request):
        self.requests.append(request)
        return AgentTaskRuntimeResult(
            agent_key="surface",
            body="Поверхность изменилась. Запуск инструментов не выполняю.",
            message_kind=AgentTaskMessageKind.FINDING,
            status=AgentTaskStatus.WAITING,
            metadata={"runtime": "test"},
        )


def _message():
    task_id = uuid4()
    source_message_id = uuid4()
    return {
        "id": uuid4(),
        "program_id": uuid4(),
        "campaign_id": uuid4(),
        "correlation_id": uuid4(),
        "message_type": AGENT_TASK_PROMPT_MESSAGE_TYPE,
        "locked_by": "test-worker",
        "payload": {
            "schema_version": AGENT_TASK_PROMPT_SCHEMA_VERSION,
            "task_id": str(task_id),
            "message_id": str(source_message_id),
            "target_agent": "surface",
            "prompt_excerpt": "объясни изменения поверхности",
            "prompt_hash": "a" * 64,
            "context_refs": [{"kind": "surface", "id": "api/account"}],
            "metadata": {"agent_runtime_mode": "none"},
        },
    }


@pytest.mark.asyncio
async def test_langgraph_agent_worker_claims_runs_and_ingests_typed_result() -> None:
    message = _message()
    client = RecordingClient([message])
    runtime = RecordingRuntime()
    worker = LangGraphAgentTaskWorker(
        client=client,
        runtime=runtime,
        program_id=message["program_id"],
        consumer_id="test-worker",
        claim_limit=3,
        lease_seconds=60,
    )

    sweep = await worker.process_once()

    assert sweep.claimed == 1
    assert sweep.processed == 1
    assert sweep.failed == 0
    assert client.claims[0]["program_id"] == message["program_id"]
    assert runtime.requests[0].target_agent == "surface"
    payload = client.ingested[0]
    assert payload["task_id"] == message["payload"]["task_id"]
    assert payload["source_message_id"] == message["payload"]["message_id"]
    assert payload["inbox_message_id"] == str(message["id"])
    assert payload["message_kind"] == "finding"
    assert payload["status"] == "waiting"
    assert payload["ack_inbox"] is True
    assert payload["metadata"]["worker"]["name"] == "langgraph-agent-task-worker"


def test_agent_worker_does_not_expose_tool_execution_shortcuts() -> None:
    service_root = Path("services/agent-worker")
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in service_root.rglob("*.py")
    )
    forbidden = ("subprocess", "shell=True", "RabbitMQ", "event_bus.publish")
    for token in forbidden:
        assert token not in combined


def test_agent_worker_client_claims_only_agent_task_messages_by_type() -> None:
    source = Path("services/agent-worker/agent_worker/client.py").read_text(encoding="utf-8")
    assert "AGENT_TASK_PROMPT_MESSAGE_TYPE" in source
    assert "\"message_type\": AGENT_TASK_PROMPT_MESSAGE_TYPE" in source
