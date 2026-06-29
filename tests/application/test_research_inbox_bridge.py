from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from api.application.research_inbox_bridge import (
    ResearchInboxBridge,
    hypothesis_request_from_inbox_message,
    research_thread_id_for_inbox_message,
)


@dataclass
class Snapshot:
    values: dict


class RecordingGraph:
    def __init__(self, *, existing_values=None) -> None:
        self.existing_values = existing_values or {}
        self.invoked = []
        self.resumed = []
        self.state_lookups = []

    async def ainvoke(self, request, *, thread_id, required_projections=()):
        self.invoked.append((request, thread_id, required_projections))
        return {"status": "started", "thread_id": thread_id}

    async def aresume(self, *, thread_id):
        self.resumed.append(thread_id)
        return {"status": "resumed", "thread_id": thread_id}

    async def aget_state(self, *, thread_id):
        self.state_lookups.append(thread_id)
        return Snapshot(values=self.existing_values)


class RecordingInboxStore:
    def __init__(self) -> None:
        self.acked = []

    async def ack_inbox_message(self, *, message_id):
        self.acked.append(message_id)


class RecordingWorkflowStatusReader:
    def __init__(self, status: str | None) -> None:
        self.status = status
        self.lookups = []

    async def get_workflow_run_status(self, *, run_id):
        self.lookups.append(run_id)
        return self.status


def _message(**overrides):
    message = {
        "id": uuid4(),
        "program_id": uuid4(),
        "campaign_id": uuid4(),
        "workflow_id": None,
        "workflow_run_id": None,
        "payload": {
            "hypothesis_build_request": {
                "result_key": "surface:admin",
                "limit": 50,
            }
        },
    }
    message.update(overrides)
    return message


def test_inbox_message_without_workflow_run_gets_stable_thread_id() -> None:
    message = _message()

    assert research_thread_id_for_inbox_message(message) == f"agent-inbox:{message['id']}"


def test_inbox_message_with_workflow_run_resumes_existing_thread_id() -> None:
    run_id = uuid4()
    message = _message(workflow_run_id=run_id)

    assert research_thread_id_for_inbox_message(message) == str(run_id)


def test_hypothesis_request_from_inbox_message_copies_only_pointer_fields() -> None:
    program_id = uuid4()
    campaign_id = uuid4()
    action_id = uuid4()
    message = _message(
        program_id=program_id,
        campaign_id=campaign_id,
        payload={
            "payload": {
                "result_key": "surface:api",
                "action_id": str(action_id),
                "limit": 500,
                "body": "must not enter graph state",
            }
        },
    )

    request = hypothesis_request_from_inbox_message(message)

    assert request.program_id == program_id
    assert request.campaign_id == campaign_id
    assert request.action_id == action_id
    assert request.result_key == "surface:api"
    assert request.limit == 100
    assert "body" not in repr(request)


async def test_handoff_starts_graph_once_and_acks_after_persisted_invoke() -> None:
    message = _message()
    graph = RecordingGraph()
    inbox_store = RecordingInboxStore()
    handoff = ResearchInboxBridge(graph=graph, inbox_store=inbox_store)

    result = await handoff.handoff(message)

    assert result.outcome == "started"
    assert result.mode == "start"
    assert result.action == "start_graph"
    assert result.thread_id == f"agent-inbox:{message['id']}"
    assert len(graph.invoked) == 1
    assert graph.invoked[0][1] == result.thread_id
    assert inbox_store.acked == [message["id"]]


async def test_handoff_acks_existing_checkpoint_without_duplicate_invoke() -> None:
    message = _message()
    graph = RecordingGraph(existing_values={"hypothesis_ids": []})
    inbox_store = RecordingInboxStore()
    handoff = ResearchInboxBridge(graph=graph, inbox_store=inbox_store)

    result = await handoff.handoff(message)

    assert result.outcome == "already_started"
    assert result.action == "ack_existing_checkpoint"
    assert graph.invoked == []
    assert inbox_store.acked == [message["id"]]


async def test_handoff_resumes_existing_workflow_run_and_acks() -> None:
    run_id = uuid4()
    message = _message(workflow_run_id=run_id)
    graph = RecordingGraph()
    inbox_store = RecordingInboxStore()
    handoff = ResearchInboxBridge(graph=graph, inbox_store=inbox_store)

    result = await handoff.handoff(message)

    assert result.outcome == "resumed"
    assert result.mode == "resume"
    assert result.action == "resume_graph"
    assert result.thread_id == str(run_id)
    assert graph.resumed == [str(run_id)]
    assert graph.invoked == []
    assert inbox_store.acked == [message["id"]]


async def test_handoff_does_not_resume_cancelled_workflow_run() -> None:
    run_id = uuid4()
    message = _message(workflow_run_id=run_id)
    graph = RecordingGraph()
    inbox_store = RecordingInboxStore()
    status_reader = RecordingWorkflowStatusReader("cancelled")
    handoff = ResearchInboxBridge(
        graph=graph,
        inbox_store=inbox_store,
        workflow_state_reader=status_reader,
    )

    result = await handoff.handoff(message)

    assert result.outcome == "skipped_terminal_workflow"
    assert result.mode == "workflow_cancelled"
    assert result.action == "ack_without_resume"
    assert result.reason_code == "workflow_cancelled"
    assert result.workflow_status == "cancelled"
    assert graph.resumed == []
    assert graph.invoked == []
    assert inbox_store.acked == [message["id"]]
    assert status_reader.lookups == [run_id]


async def test_handoff_resumes_non_terminal_workflow_run_after_status_check() -> None:
    run_id = uuid4()
    message = _message(workflow_run_id=run_id)
    graph = RecordingGraph()
    inbox_store = RecordingInboxStore()
    status_reader = RecordingWorkflowStatusReader("waiting")
    handoff = ResearchInboxBridge(
        graph=graph,
        inbox_store=inbox_store,
        workflow_state_reader=status_reader,
    )

    result = await handoff.handoff(message)

    assert result.outcome == "resumed"
    assert result.action == "resume_graph"
    assert graph.resumed == [str(run_id)]
    assert inbox_store.acked == [message["id"]]
