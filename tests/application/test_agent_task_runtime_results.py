from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from api.application.agent_action_proposals import (
    AgentActionProposalDraft,
    AgentActionProposalRecord,
    AgentActionProposalStatus,
    AgentActionProposalType,
)
from api.application.agent_task_runtime_results import (
    AgentTaskRuntimeResultIngestRequest,
    AgentTaskRuntimeResultIngestService,
)
from api.application.agent_tasks import (
    AgentTaskMessageKind,
    AgentTaskMessageRecord,
    AgentTaskMessageRole,
    AgentTaskStatus,
    body_hash,
    utcnow,
)


class RecordingTaskService:
    def __init__(self) -> None:
        self.replies = []

    async def append_agent_reply(self, *, task_id, request):
        self.replies.append((task_id, request))

        return AgentTaskMessageRecord(
            message_id=uuid4(),
            task_id=task_id,
            program_id=uuid4(),
            campaign_id=None,
            correlation_id=uuid4(),
            role=AgentTaskMessageRole.AGENT,
            message_kind=request.message_kind,
            agent_key=request.agent_key,
            body=request.body,
            body_hash=body_hash(request.body),
            proposal_refs=request.proposal_refs,
            metadata=request.metadata,
            created_at=utcnow(),
        )


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


class RecordingAckStore:
    def __init__(self) -> None:
        self.acked = []

    async def ack_inbox_message(self, *, message_id):
        self.acked.append(message_id)


@pytest.mark.asyncio
async def test_runtime_result_ingest_writes_proposals_reply_and_acks() -> None:
    task_id = uuid4()
    source_message_id = uuid4()
    inbox_message_id = uuid4()
    program_id = uuid4()
    campaign_id = uuid4()
    task_service = RecordingTaskService()
    proposal_writer = RecordingProposalWriter()
    ack_store = RecordingAckStore()
    service = AgentTaskRuntimeResultIngestService(
        task_service=task_service,
        proposal_writer=proposal_writer,
        ack_store=ack_store,
    )

    result = await service.ingest(
        AgentTaskRuntimeResultIngestRequest(
            task_id=task_id,
            source_message_id=source_message_id,
            program_id=program_id,
            campaign_id=campaign_id,
            inbox_message_id=inbox_message_id,
            agent_key="coordinator",
            body="Предлагаю разобрать JS без прямого запуска инструментов.",
            message_kind=AgentTaskMessageKind.PROPOSAL,
            status=AgentTaskStatus.WAITING,
            proposal_drafts=[
                AgentActionProposalDraft(
                    proposal_type=AgentActionProposalType.INVESTIGATION_TASK,
                    title="Разобрать JS-пути",
                    summary="Сохранить proposal на review без запуска инструмента.",
                    action_intent="review_js_paths",
                )
            ],
            metadata={"runtime": "langgraph"},
        )
    )

    assert result.task_id == task_id
    assert result.inbox_acknowledged is True
    assert ack_store.acked == [inbox_message_id]
    assert len(proposal_writer.calls) == 1
    assert proposal_writer.calls[0]["source_message_id"] == source_message_id
    assert len(task_service.replies) == 1
    _, reply = task_service.replies[0]
    assert reply.message_kind is AgentTaskMessageKind.PROPOSAL
    assert reply.status is AgentTaskStatus.WAITING
    assert reply.metadata["runtime_result_boundary"]["runtime_owner"] == "langgraph"
    assert reply.metadata["runtime_result_boundary"]["tool_execution"] == "forbidden_from_runtime_result_ingest"
    assert reply.proposal_refs[0]["kind"] == "agent_action_proposal"


@pytest.mark.asyncio
async def test_runtime_result_ingest_can_append_reply_without_ack() -> None:
    task_service = RecordingTaskService()
    ack_store = RecordingAckStore()
    service = AgentTaskRuntimeResultIngestService(
        task_service=task_service,
        proposal_writer=None,
        ack_store=ack_store,
    )

    result = await service.ingest(
        AgentTaskRuntimeResultIngestRequest(
            task_id=uuid4(),
            source_message_id=uuid4(),
            program_id=uuid4(),
            agent_key="critic",
            body="Это похоже на повтор. Инструменты не запускаю.",
            message_kind=AgentTaskMessageKind.QUESTION,
            ack_inbox=False,
        )
    )

    assert result.inbox_acknowledged is False
    assert ack_store.acked == []
    assert len(task_service.replies) == 1
