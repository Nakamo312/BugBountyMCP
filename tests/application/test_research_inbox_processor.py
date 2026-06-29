from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import uuid4

from api.application.research_inbox_bridge import ResearchInboxProcessor, ResearchInboxProcessorSweep


class GraphDependency: ...


@dataclass
class Snapshot:
    values: dict


class RecordingGraph:
    def __init__(self, *, fail: bool = False, existing_threads=None) -> None:
        self.fail = fail
        self.existing_threads = set(existing_threads or [])
        self.invoked = []
        self.resumed = []
        self.state_lookups = []

    async def ainvoke(self, request, *, thread_id, required_projections=()):
        if self.fail:
            raise RuntimeError("graph unavailable")
        self.invoked.append((request, thread_id, required_projections))
        return {"status": "started"}

    async def aresume(self, *, thread_id):
        self.resumed.append(thread_id)
        return {"status": "resumed"}

    async def aget_state(self, *, thread_id):
        self.state_lookups.append(thread_id)
        return Snapshot(values={"thread_id": thread_id} if thread_id in self.existing_threads else {})


class RecordingRequestContainer:
    def __init__(self, graph) -> None:
        self.graph = graph
        self.requested = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def get(self, dependency):
        self.requested.append(dependency)
        assert dependency is GraphDependency
        return self.graph


class RecordingContainerFactory:
    def __init__(self, graph) -> None:
        self.graph = graph
        self.opened = []

    def __call__(self):
        container = RecordingRequestContainer(self.graph)
        self.opened.append(container)
        return container


class RecordingInboxStore:
    def __init__(self, messages, *, workflow_statuses=None) -> None:
        self.messages = list(messages)
        self.workflow_statuses = dict(workflow_statuses or {})
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

    async def get_workflow_run_status(self, *, run_id):
        return self.workflow_statuses.get(run_id)


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
            }
        },
    }
    message.update(overrides)
    return message


async def test_inbox_processor_claims_by_inbox_key_and_handoffs_messages() -> None:
    message = _message()
    graph = RecordingGraph()
    store = RecordingInboxStore([message])
    processor = ResearchInboxProcessor(
        container=RecordingContainerFactory(graph),
        inbox_store=store,
        consumer_id="worker-1",
        inbox_key="mvp-hypothesis-builder",
        claim_limit=10,
        lease_seconds=120,
        graph_dependency=GraphDependency,
    )

    processed = await processor.process_once()

    assert processed == 1
    assert store.claims == [
        {
            "program_id": None,
            "campaign_id": None,
            "correlation_id": None,
            "inbox_key": "mvp-hypothesis-builder",
            "consumer_id": "worker-1",
            "lease_seconds": 120,
            "limit": 10,
        }
    ]
    assert store.acked == [message["id"]]
    assert graph.invoked[0][1] == f"agent-inbox:{message['id']}"


async def test_inbox_processor_leaves_message_claimed_when_graph_handoff_fails() -> None:
    message = _message()
    graph = RecordingGraph(fail=True)
    store = RecordingInboxStore([message])
    processor = ResearchInboxProcessor(
        container=RecordingContainerFactory(graph),
        inbox_store=store,
        consumer_id="worker-1",
        inbox_key="mvp-hypothesis-builder",
        graph_dependency=GraphDependency,
    )

    processed = await processor.process_once()

    assert processed == 0
    assert store.acked == []
    assert store.errors == [(message["id"], "RuntimeError: graph unavailable")]
    assert len(store.claims) == 1


def test_inbox_processor_is_wired_as_lifespan_worker_but_disabled_by_default() -> None:
    app_source = open("src/api/presentation/rest/app.py", encoding="utf-8").read()
    di_source = open("src/api/application/di.py", encoding="utf-8").read()
    config_source = open("src/api/config.py", encoding="utf-8").read()

    assert "ResearchInboxProcessor" in di_source
    assert "USE_AGENT_INBOX_PROCESSOR: bool = False" in config_source
    assert "inbox_processor.start()" in app_source
    assert "inbox_processor.stop()" in app_source

async def test_inbox_processor_keeps_processing_after_recording_failure_error_fails() -> None:
    message = _message()
    graph = RecordingGraph(fail=True)
    store = RecordingInboxStore([message])

    async def fail_to_record(*, message_id, error):
        raise RuntimeError("store unavailable")

    store.record_inbox_handoff_error = fail_to_record
    processor = ResearchInboxProcessor(
        container=RecordingContainerFactory(graph),
        inbox_store=store,
        consumer_id="worker-1",
        inbox_key="mvp-hypothesis-builder",
        graph_dependency=GraphDependency,
    )

    processed = await processor.process_once()

    assert processed == 0
    assert store.acked == []


def test_processor_sweep_default_values() -> None:
    summary = ResearchInboxProcessorSweep()

    assert summary.claimed == 0
    assert summary.processed == 0


async def test_inbox_processor_summary_counts_handoff_outcomes() -> None:
    start_message = _message()
    existing_message = _message()
    resumed_run_id = uuid4()
    resumed_message = _message(workflow_run_id=resumed_run_id)
    cancelled_run_id = uuid4()
    cancelled_message = _message(workflow_run_id=cancelled_run_id)
    existing_thread_id = f"agent-inbox:{existing_message['id']}"
    graph = RecordingGraph(existing_threads={existing_thread_id})
    store = RecordingInboxStore(
        [start_message, existing_message, resumed_message, cancelled_message],
        workflow_statuses={
            resumed_run_id: "waiting",
            cancelled_run_id: "cancelled",
        },
    )
    processor = ResearchInboxProcessor(
        container=RecordingContainerFactory(graph),
        inbox_store=store,
        consumer_id="worker-1",
        inbox_key="mvp-hypothesis-builder",
        graph_dependency=GraphDependency,
    )

    summary = await processor.process_once_summary()

    assert summary.claimed == 4
    assert summary.handed_off == 4
    assert summary.acknowledged == 4
    assert summary.started == 1
    assert summary.already_started == 1
    assert summary.resumed == 1
    assert summary.skipped_terminal_workflow == 1
    assert summary.failed == 0
    assert graph.invoked[0][1] == f"agent-inbox:{start_message['id']}"
    assert graph.resumed == [str(resumed_run_id)]


async def test_inbox_processor_summary_counts_handoff_failures() -> None:
    message = _message()
    graph = RecordingGraph(fail=True)
    store = RecordingInboxStore([message])
    processor = ResearchInboxProcessor(
        container=RecordingContainerFactory(graph),
        inbox_store=store,
        consumer_id="worker-1",
        inbox_key="mvp-hypothesis-builder",
        graph_dependency=GraphDependency,
    )

    summary = await processor.process_once_summary()

    assert summary.claimed == 1
    assert summary.handed_off == 0
    assert summary.acknowledged == 0
    assert summary.failed == 1
    assert store.errors == [(message["id"], "RuntimeError: graph unavailable")]


async def test_inbox_processor_logs_one_sweep_summary(caplog) -> None:
    start_message = _message()
    cancelled_run_id = uuid4()
    cancelled_message = _message(workflow_run_id=cancelled_run_id)
    graph = RecordingGraph()
    store = RecordingInboxStore(
        [start_message, cancelled_message],
        workflow_statuses={cancelled_run_id: "cancelled"},
    )
    processor = ResearchInboxProcessor(
        container=RecordingContainerFactory(graph),
        inbox_store=store,
        consumer_id="worker-1",
        inbox_key="research-hypothesis-builder",
        graph_dependency=GraphDependency,
    )

    with caplog.at_level(logging.INFO, logger="api.application.research_inbox_bridge"):
        summary = await processor.process_once_summary()

    assert summary.claimed == 2
    records = [
        record
        for record in caplog.records
        if record.message == "research inbox sweep completed"
    ]
    assert len(records) == 1
    record = records[0]
    assert record.research_inbox_consumer_id == "worker-1"
    assert record.research_inbox_key == "research-hypothesis-builder"
    assert record.research_inbox_claimed == 2
    assert record.research_inbox_started == 1
    assert record.research_inbox_skipped_terminal_workflow == 1
    assert record.research_inbox_failed == 0


async def test_inbox_processor_logs_empty_sweep_at_debug_level(caplog) -> None:
    graph = RecordingGraph()
    store = RecordingInboxStore([])
    processor = ResearchInboxProcessor(
        container=RecordingContainerFactory(graph),
        inbox_store=store,
        consumer_id="worker-1",
        inbox_key="research-hypothesis-builder",
        graph_dependency=GraphDependency,
    )

    with caplog.at_level(logging.DEBUG, logger="api.application.research_inbox_bridge"):
        summary = await processor.process_once_summary()

    assert summary.claimed == 0
    records = [
        record
        for record in caplog.records
        if record.message == "research inbox sweep completed"
    ]
    assert len(records) == 1
    assert records[0].levelno == logging.DEBUG
    assert records[0].research_inbox_claimed == 0
