from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from api.application.agent_task_budget import BudgetedAgentTaskRuntime
from api.application.agent_task_inbox_bridge import (
    BoundedAgentTaskRuntime,
    AgentTaskRuntimeRequest,
)
from api.application.agent_task_langgraph_runtime import (
    AgentTaskRuntimeFactory,
    LangGraphAgentTaskRuntime,
    LangGraphAgentTaskGraphRunner,
    agent_task_langgraph_thread_ref,
)
from api.application.agent_tasks import AgentTaskMessageKind, AgentTaskStatus


class RecordingContextReader:
    def __init__(self) -> None:
        self.requests = []

    async def read(self, request: AgentTaskRuntimeRequest) -> dict:
        self.requests.append(request)
        return {
            "program_id": str(request.program_id),
            "task_id": str(request.task_id),
            "message_id": str(request.message_id),
            "context_refs": [{"kind": "surface", "id": "api/account"}],
        }


class RecordingGraphRunner:
    def __init__(self) -> None:
        self.calls = []

    async def ainvoke(self, *, request: AgentTaskRuntimeRequest, context: dict) -> dict:
        self.calls.append((request, context))
        return {
            "agent_key": "surface",
            "body": "Нашёл новую ветку account/*. Нужна bounded проверка.",
            "message_kind": "proposal",
            "status": "waiting",
            "graph_refs": [{"kind": "branch", "id": "api/account"}],
            "proposal_refs": [{"proposal_id": str(uuid4())}],
            "metadata": {"runtime": "test-langgraph"},
            "boundary": {"tool_execution": "runner_attempted_override"},
        }


def _request() -> AgentTaskRuntimeRequest:
    return AgentTaskRuntimeRequest(
        task_id=uuid4(),
        message_id=uuid4(),
        program_id=uuid4(),
        campaign_id=uuid4(),
        correlation_id=uuid4(),
        target_agent="surface",
        schema_version="agent-task-prompt.v1",
        body_excerpt="Разбери новую ветку api/account/*",
        body_hash="a" * 64,
        context_refs=({"kind": "surface", "id": "api/account"},),
        metadata={"ui": "campaign-workspace"},
        source="ui",
    )


def test_agent_task_langgraph_thread_ref_is_deterministic_and_sanitized() -> None:
    task_id = uuid4()

    thread_ref = agent_task_langgraph_thread_ref(
        task_id,
        checkpoint_ns="Agent Task Unsafe / Namespace!",
    )

    assert thread_ref.thread_id == f"agent-task:{task_id}"
    assert thread_ref.checkpoint_ns == "agenttaskunsafenamespace"
    assert thread_ref.config() == {
        "configurable": {
            "thread_id": f"agent-task:{task_id}",
            "checkpoint_ns": "agenttaskunsafenamespace",
        }
    }
    assert thread_ref.to_metadata()["owner"] == "langgraph"
    assert thread_ref.to_metadata()["domain_task_id"] == str(task_id)


@pytest.mark.asyncio
async def test_langgraph_runner_invokes_graph_with_task_thread_config() -> None:
    class FakeCompiled:
        def __init__(self) -> None:
            self.calls = []

        async def ainvoke(self, state: dict, *, config: dict) -> dict:
            self.calls.append((state, config))
            return {
                "agent_key": "coordinator",
                "body": "ok",
                "message_kind": "note",
                "status": "waiting",
                "metadata": {"runtime": "fake"},
            }

    request = _request()
    compiled = FakeCompiled()
    runner = LangGraphAgentTaskGraphRunner.__new__(LangGraphAgentTaskGraphRunner)
    runner._compiled = compiled
    runner._checkpoint_ns = "agent-task"

    result = await runner.ainvoke(request=request, context={"context_refs": []})

    assert result["body"] == "ok"
    state, config = compiled.calls[0]
    assert state["langgraph_thread_id"] == f"agent-task:{request.task_id}"
    assert state["langgraph_checkpoint_ns"] == "agent-task"
    assert config == {
        "configurable": {
            "thread_id": f"agent-task:{request.task_id}",
            "checkpoint_ns": "agent-task",
        }
    }


@pytest.mark.asyncio
async def test_langgraph_runtime_maps_graph_state_to_visible_agent_reply() -> None:
    context_reader = RecordingContextReader()
    graph_runner = RecordingGraphRunner()
    runtime = LangGraphAgentTaskRuntime(
        runner=graph_runner,
        context_reader=context_reader,
    )
    request = _request()

    result = await runtime.handle(request)

    assert context_reader.requests == [request]
    assert graph_runner.calls[0][0] == request
    assert graph_runner.calls[0][1]["context_refs"] == [{"kind": "surface", "id": "api/account"}]
    assert result.agent_key == "surface"
    assert result.body.startswith("Нашёл новую ветку")
    assert result.message_kind is AgentTaskMessageKind.PROPOSAL
    assert result.status is AgentTaskStatus.WAITING
    assert result.graph_refs == ({"kind": "branch", "id": "api/account"},)
    assert result.proposal_refs
    assert result.metadata["runtime"] == "test-langgraph"
    assert result.metadata["source_message_id"] == str(request.message_id)
    assert result.metadata["langgraph_thread_id"] == f"agent-task:{request.task_id}"
    assert result.metadata["langgraph_thread"]["owner"] == "langgraph"
    assert result.metadata["context_ref_count"] == 1
    assert result.metadata["boundary"]["tool_execution"] == "forbidden_from_langgraph_agent_task_runtime"
    assert result.metadata["boundary"]["raw_artifact_access"] == "forbidden"


@pytest.mark.asyncio
async def test_langgraph_runtime_uses_safe_fallback_reply_when_graph_returns_no_body() -> None:
    class EmptyGraphRunner:
        async def ainvoke(self, *, request: AgentTaskRuntimeRequest, context: dict) -> dict:
            return {"message_kind": "finding", "status": "running"}

    runtime = LangGraphAgentTaskRuntime(
        runner=EmptyGraphRunner(),
        context_reader=RecordingContextReader(),
    )

    result = await runtime.handle(_request())

    assert result.message_kind is AgentTaskMessageKind.FINDING
    assert result.status is AgentTaskStatus.WAITING
    assert "workflow не вернул текст" in result.body
    assert result.metadata["boundary"]["tool_execution"] == "forbidden_from_langgraph_agent_task_runtime"


def test_agent_task_runtime_factory_keeps_bounded_default() -> None:
    runtime = AgentTaskRuntimeFactory("bounded").create()

    assert isinstance(runtime, BudgetedAgentTaskRuntime)
    assert isinstance(runtime.inner, BoundedAgentTaskRuntime)


def test_agent_task_runtime_factory_rejects_unknown_runtime() -> None:
    with pytest.raises(ValueError):
        AgentTaskRuntimeFactory("shell").create()


def test_langgraph_agent_task_runtime_does_not_import_execution_surfaces() -> None:
    source = Path("src/api/application/agent_task_langgraph_runtime.py").read_text(encoding="utf-8")

    assert "ActionService" not in source
    assert "RabbitMQ" not in source
    assert "subprocess" not in source
    assert "runner" in source
    assert "forbidden_from_langgraph_agent_task_runtime" in source
    assert "agent_task_langgraph_thread_ref" in source
    assert "thread_id" in source

@pytest.mark.asyncio
async def test_langgraph_role_graph_is_deterministic_dispatch_boundary() -> None:
    runner = LangGraphAgentTaskGraphRunner.__new__(LangGraphAgentTaskGraphRunner)
    from api.application.agent_task_roles import AgentTaskRoleComposer

    runner._role_composer = AgentTaskRoleComposer()
    state = {
        "target_agent": "surface",
        "body_excerpt": "посмотри surface refs",
        "context": {"context_refs": [{"kind": "surface", "id": "api/account"}]},
        "message_id": str(uuid4()),
        "task_id": str(uuid4()),
        "langgraph_thread_id": "agent-task:test",
        "langgraph_checkpoint_ns": "agent-task",
    }

    guarded = await runner._guard_boundary(state)
    composed = await runner._compose_role_reply({**state, **guarded})

    assert guarded["agent_route"] == "surface"
    assert guarded["metadata"]["graph_kind"] == "deterministic_role_dispatch"
    assert composed["agent_key"] == "surface"
    assert composed["metadata"]["graph"] == "agent-task-deterministic-role-dispatch.v1"
