from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

import pytest

from api.application.agent_action_proposals import (
    AgentActionProposalDraft,
    AgentActionProposalRecord,
    AgentActionProposalStatus,
    AgentActionProposalType,
)
from api.application.agent_task_inbox_bridge import (
    AgentTaskInboxBridge,
    AgentTaskInboxProcessor,
    AgentTaskRuntimeRequest,
    AgentTaskRuntimeResult,
    BoundedAgentTaskRuntime,
    runtime_request_from_agent_task_message,
)
from api.application.agent_tasks import (
    AGENT_TASK_PROMPT_MESSAGE_TYPE,
    AGENT_TASK_PROMPT_SCHEMA_VERSION,
    AgentTaskMessageKind,
    AgentTaskStatus,
)


class RecordingInboxStore:
    def __init__(self, messages=None) -> None:
        self.messages = list(messages or [])
        self.claims = []
        self.acked = []
        self.errors = []

    async def claim_inbox(self, **kwargs):
        self.claims.append(kwargs)
        return list(self.messages)

    async def ack_inbox_message(self, *, message_id):
        self.acked.append(message_id)

    async def record_inbox_handoff_error(self, *, message_id, error):
        self.errors.append((message_id, error))


class RecordingTaskService:
    def __init__(self) -> None:
        self.replies = []

    async def append_agent_reply(self, *, task_id, request):
        self.replies.append((task_id, request))

        @dataclass
        class Reply:
            message_id: object

        return Reply(message_id=uuid4())




class RecordingProposalWriter:
    def __init__(self) -> None:
        self.calls = []

    async def write_agent_task_proposals(self, **kwargs):
        self.calls.append(kwargs)
        draft = kwargs["drafts"][0]
        return (
            AgentActionProposalRecord(
                proposal_id=uuid4(),
                program_id=kwargs["program_id"],
                campaign_id=kwargs["campaign_id"],
                task_id=kwargs["task_id"],
                source_message_id=kwargs["source_message_id"],
                agent_key=kwargs["agent_key"],
                proposal_key="agent-task:test:proposal",
                proposal_type=draft.proposal_type,
                status=AgentActionProposalStatus.PENDING,
                title=draft.title,
                summary=draft.summary,
                rationale=draft.rationale or "",
                capability_id=draft.capability_id,
                profile_id=draft.profile_id,
                priority=draft.priority,
                risk_level=draft.risk_level,
                expected_gain=draft.expected_gain or "",
                action_intent=draft.action_intent or "",
                action_params=draft.action_params,
                context_refs=draft.context_refs,
                metadata=draft.metadata,
                produced_by="test",
            ),
        )

class RecordingRuntime:
    def __init__(self) -> None:
        self.requests = []

    async def handle(self, request: AgentTaskRuntimeRequest) -> AgentTaskRuntimeResult:
        self.requests.append(request)
        return AgentTaskRuntimeResult(
            agent_key="coordinator",
            body="Нашёл направление. Нужен выбор оператора.",
            message_kind=AgentTaskMessageKind.PROPOSAL,
            status=AgentTaskStatus.WAITING,
            proposal_refs=({"proposal_id": str(uuid4())},),
            metadata={"runtime": "test"},
        )


def _message(**payload_overrides):
    task_id = uuid4()
    source_message_id = uuid4()
    payload = {
        "schema_version": AGENT_TASK_PROMPT_SCHEMA_VERSION,
        "task_id": str(task_id),
        "message_id": str(source_message_id),
        "target_agent": "coordinator",
        "prompt_excerpt": "Разбери новые JS-пути без запуска инструментов из промта",
        "prompt_hash": "a" * 64,
        "context_refs": [{"kind": "surface", "id": "api/account"}],
        "metadata": {"note": "safe"},
    }
    payload.update(payload_overrides)
    return {
        "id": uuid4(),
        "program_id": uuid4(),
        "campaign_id": uuid4(),
        "correlation_id": uuid4(),
        "message_type": AGENT_TASK_PROMPT_MESSAGE_TYPE,
        "payload": payload,
    }


def test_runtime_request_from_agent_task_message_is_pointer_only() -> None:
    message = _message()

    request = runtime_request_from_agent_task_message(message)

    assert request.task_id == uuid4() or str(request.task_id) == message["payload"]["task_id"]
    assert request.program_id == message["program_id"]
    assert request.target_agent == "coordinator"
    assert "JS-пути" in request.body_excerpt
    assert request.context_refs == ({"kind": "surface", "id": "api/account"},)


@pytest.mark.asyncio
async def test_bridge_appends_agent_reply_then_acks_inbox_message() -> None:
    message = _message()
    inbox = RecordingInboxStore()
    task_service = RecordingTaskService()
    runtime = RecordingRuntime()
    bridge = AgentTaskInboxBridge(
        runtime=runtime,
        task_service=task_service,
        inbox_store=inbox,
    )

    result = await bridge.handoff(message)

    assert result.outcome == "processed"
    assert result.acknowledged is True
    assert inbox.acked == [message["id"]]
    assert len(task_service.replies) == 1
    task_id, reply_request = task_service.replies[0]
    assert str(task_id) == message["payload"]["task_id"]
    assert reply_request.agent_key == "coordinator"
    assert reply_request.message_kind is AgentTaskMessageKind.PROPOSAL
    assert reply_request.status is AgentTaskStatus.WAITING
    assert reply_request.metadata["agent_task_inbox_message_id"] == str(message["id"])
    assert reply_request.proposal_refs


@pytest.mark.asyncio
async def test_bridge_persists_runtime_proposal_drafts_before_visible_reply() -> None:
    message = _message()
    inbox = RecordingInboxStore()
    task_service = RecordingTaskService()

    class RuntimeWithDraft:
        async def handle(self, request: AgentTaskRuntimeRequest) -> AgentTaskRuntimeResult:
            return AgentTaskRuntimeResult(
                agent_key="coordinator",
                body="Предлагаю сохранить следующий шаг для review.",
                message_kind=AgentTaskMessageKind.PROPOSAL,
                status=AgentTaskStatus.WAITING,
                proposal_drafts=(
                    AgentActionProposalDraft(
                        proposal_type=AgentActionProposalType.INVESTIGATION_TASK,
                        title="Разобрать JS-пути",
                        summary="Сохранить proposal на review, не запуская инструмент напрямую.",
                        action_intent="review_js_paths",
                    ),
                ),
                metadata={"runtime": "test"},
            )

    writer = RecordingProposalWriter()
    bridge = AgentTaskInboxBridge(
        runtime=RuntimeWithDraft(),
        task_service=task_service,
        inbox_store=inbox,
        proposal_writer=writer,
    )

    result = await bridge.handoff(message)

    assert result.outcome == "processed"
    assert len(writer.calls) == 1
    assert writer.calls[0]["task_id"] == result.task_id
    _, reply_request = task_service.replies[0]
    assert reply_request.proposal_refs[0]["kind"] == "agent_action_proposal"
    assert reply_request.proposal_refs[0]["approval"] == "required_via_action_service"
    assert reply_request.metadata["agent_action_proposals_created"] == 1
    assert reply_request.metadata["proposal_boundary"]["action_service_required"] is True


@pytest.mark.asyncio
async def test_processor_claims_only_agent_task_messages_by_type() -> None:
    message = _message()
    inbox = RecordingInboxStore(messages=[message])
    task_service = RecordingTaskService()

    class Container:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, dependency):
            assert dependency.__name__ == "AgentTaskService"
            return task_service

    processor = AgentTaskInboxProcessor(
        container=lambda: Container(),
        inbox_store=inbox,
        runtime=RecordingRuntime(),
        consumer_id="test-agent-task-worker",
    )

    summary = await processor.process_once_summary()

    assert summary.claimed == 1
    assert summary.processed == 1
    assert summary.acknowledged == 1
    assert inbox.claims[0]["message_type"] == AGENT_TASK_PROMPT_MESSAGE_TYPE
    assert inbox.claims[0]["consumer_id"] == "test-agent-task-worker"
    assert len(task_service.replies) == 1


@pytest.mark.asyncio
async def test_bounded_runtime_returns_visible_waiting_reply_without_tool_execution() -> None:
    runtime = BoundedAgentTaskRuntime()
    request = runtime_request_from_agent_task_message(_message())

    result = await runtime.handle(request)

    assert result.status is AgentTaskStatus.WAITING
    assert result.message_kind is AgentTaskMessageKind.QUESTION
    assert "не буду запускать инструменты" in result.body
    assert result.metadata["boundary"]["tool_execution"] == "forbidden_from_agent_task_runtime"
