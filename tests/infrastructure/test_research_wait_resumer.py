from __future__ import annotations

import os
import subprocess
import sys
from uuid import uuid4

import pytest

pytest.importorskip("langgraph")

from api.application.agent_wait_conditions import (
    AgentWaitConditionProcessor,
    AgentWaitConditionRecord,
    WaitConditionDecision,
)
from api.application.hypotheses import HypothesisBuildRequest
from api.application.research_readiness import ResearchReadinessDecision
from api.application.research_control_graph import ResearchControlGraph
from api.application.research_pass import ResearchPassResult
from api.infrastructure.langgraph_resume import ResearchWaitResumer


class RecordingGraph:
    def __init__(self) -> None:
        self.thread_ids = []

    async def aresume(self, *, thread_id: str):
        self.thread_ids.append(thread_id)
        return {"readiness_status": "ready"}


class RequestContainer:
    def __init__(self, graph) -> None:
        self.graph = graph

    async def get(self, dependency_type):
        return self.graph


class RequestScope:
    def __init__(self, request_container) -> None:
        self.request_container = request_container

    async def __aenter__(self):
        return self.request_container

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class RecordingContainer:
    def __init__(self, graph) -> None:
        self.graph = graph
        self.scopes = 0

    def __call__(self):
        self.scopes += 1
        return RequestScope(RequestContainer(self.graph))


class StaticWorkflowStatusReader:
    def __init__(self, status: str | None) -> None:
        self.status = status
        self.run_ids = []

    async def get_workflow_run_status(self, *, run_id):
        self.run_ids.append(run_id)
        return self.status


class SequencedGate:
    def __init__(self, decisions) -> None:
        self.decisions = list(decisions)

    async def evaluate(self, request, *, required_projections):
        return self.decisions.pop(0)


class RecordingResearch:
    def __init__(self) -> None:
        self.requests = []

    async def run(self, request):
        self.requests.append(request)
        return ResearchPassResult(items=())


class ResolvedEngine:
    async def evaluate(self, condition):
        return WaitConditionDecision(
            resolved=True,
            reason="result_sets_ready",
            payload={"result_set_keys": ["surface:admin"]},
        )


class SingleWaitStore:
    def __init__(self, record) -> None:
        self.record = record

    async def list_pending(self, *, limit, now):
        record, self.record = self.record, None
        return [record] if record is not None else []

    async def list_resume_ready(self, *, limit):
        return []

    async def mark_resolved(self, **kwargs):
        return True

    async def mark_timed_out(self, **kwargs):
        return True


async def test_wait_resumer_restores_compiled_graph_by_workflow_run_id() -> None:
    workflow_run_id = uuid4()
    graph = RecordingGraph()
    container = RecordingContainer(graph)
    resumer = ResearchWaitResumer(container=container)

    await resumer.resume(
        AgentWaitConditionRecord(
            condition_id=uuid4(),
            condition_key="mvp-research:new_facts_available:abc",
            condition_type="new_facts_available",
            program_id=uuid4(),
            workflow_run_id=workflow_run_id,
        )
    )

    assert container.scopes == 1
    assert graph.thread_ids == [str(workflow_run_id)]


async def test_resolved_wait_automatically_continues_compiled_research_graph() -> None:
    memory_module = pytest.importorskip("langgraph.checkpoint.memory")
    InMemorySaver = memory_module.InMemorySaver

    workflow_run_id = uuid4()
    condition_id = uuid4()
    research = RecordingResearch()
    graph = ResearchControlGraph(
        research_workflow=research,
        readiness_gate=SequencedGate(
            [
                ResearchReadinessDecision(
                    ready=False,
                    reason="result_sets_not_ready",
                    wait_condition_id=condition_id,
                ),
                ResearchReadinessDecision(
                    ready=True,
                    reason="research_inputs_ready",
                    result_set_keys=("surface:admin",),
                ),
            ]
        ),
        checkpointer=InMemorySaver(),
    )
    request = HypothesisBuildRequest(
        program_id=uuid4(),
        workflow_run_id=workflow_run_id,
        result_key="surface:admin",
    )
    await graph.ainvoke(request, thread_id=str(workflow_run_id))
    record = AgentWaitConditionRecord(
        condition_id=condition_id,
        condition_key="mvp-research:new_facts_available:auto",
        condition_type="new_facts_available",
        program_id=request.program_id,
        workflow_run_id=workflow_run_id,
    )
    processor = AgentWaitConditionProcessor(
        store=SingleWaitStore(record),
        engine=ResolvedEngine(),
        workflow_resumer=ResearchWaitResumer(
            container=RecordingContainer(graph)
        ),
    )

    transitions = await processor.process_once()
    restored = await graph.aget_state(thread_id=str(workflow_run_id))

    assert transitions == 1
    assert restored.values["readiness_status"] == "ready"
    assert restored.values["result_set_keys"] == ["surface:admin"]
    assert research.requests == [request]


async def test_wait_resumer_skips_terminal_workflow_run() -> None:
    workflow_run_id = uuid4()
    graph = RecordingGraph()
    container = RecordingContainer(graph)
    reader = StaticWorkflowStatusReader("cancelled")
    resumer = ResearchWaitResumer(
        container=container,
        workflow_status_reader=reader,
    )

    result = await resumer.resume(
        AgentWaitConditionRecord(
            condition_id=uuid4(),
            condition_key="research:new_facts_available:abc",
            condition_type="new_facts_available",
            program_id=uuid4(),
            workflow_run_id=workflow_run_id,
        )
    )

    assert result.status == "skipped_terminal_workflow"
    assert result.thread_id == str(workflow_run_id)
    assert result.workflow_status == "cancelled"
    assert reader.run_ids == [workflow_run_id]
    assert container.scopes == 0
    assert graph.thread_ids == []


async def test_wait_resumer_reports_missing_workflow_run() -> None:
    graph = RecordingGraph()
    container = RecordingContainer(graph)
    resumer = ResearchWaitResumer(container=container)

    result = await resumer.resume(
        AgentWaitConditionRecord(
            condition_id=uuid4(),
            condition_key="research:new_facts_available:abc",
            condition_type="new_facts_available",
            program_id=uuid4(),
        )
    )

    assert result.status == "missing_workflow_run"
    assert container.scopes == 0
    assert graph.thread_ids == []


def test_wait_processor_is_started_and_stopped_with_application_lifespan() -> None:
    app_source = open("src/api/presentation/rest/app.py", encoding="utf-8").read()
    wiring_source = open("src/api/infrastructure/providers/research_runtime.py", encoding="utf-8").read()

    assert "AgentWaitConditionProcessor" in wiring_source
    assert "ResearchWaitResumer" in wiring_source
    assert "wait_condition_processor.start()" in app_source
    assert "wait_condition_processor.stop()" in app_source


def test_wait_processor_resolves_from_application_container() -> None:
    script = """
import asyncio
from api.application.agent_wait_conditions import AgentWaitConditionProcessor
from api.infrastructure.container import create_container
from api.config import Settings

async def main():
    container = create_container(context={Settings: Settings()})
    try:
        processor = await container.get(AgentWaitConditionProcessor)
        assert isinstance(processor, AgentWaitConditionProcessor)
    finally:
        await container.close()

asyncio.run(main())
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=".",
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONPATH": "src"},
    )

    assert result.returncode == 0, result.stderr
