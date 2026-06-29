from __future__ import annotations

import os
import subprocess
import sys
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver

from api.application.agent_wait_conditions import (
    AgentWaitConditionProcessor,
    AgentWaitConditionRecord,
    WaitConditionDecision,
)
from api.application.hypotheses import HypothesisBuildRequest
from api.application.mvp_research_readiness import ResearchReadinessDecision
from api.application.mvp_research_state_graph import MvpResearchStateGraph
from api.application.mvp_research_workflow import MvpResearchResult
from api.infrastructure.langgraph_resume import MvpResearchAutoResumer


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
        return MvpResearchResult(items=())


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


async def test_auto_resumer_restores_compiled_graph_by_workflow_run_id() -> None:
    workflow_run_id = uuid4()
    graph = RecordingGraph()
    container = RecordingContainer(graph)
    resumer = MvpResearchAutoResumer(container=container)

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
    workflow_run_id = uuid4()
    condition_id = uuid4()
    research = RecordingResearch()
    graph = MvpResearchStateGraph(
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
        workflow_resumer=MvpResearchAutoResumer(
            container=RecordingContainer(graph)
        ),
    )

    transitions = await processor.process_once()
    restored = await graph.aget_state(thread_id=str(workflow_run_id))

    assert transitions == 1
    assert restored.values["readiness_status"] == "ready"
    assert restored.values["result_set_keys"] == ["surface:admin"]
    assert research.requests == [request]


def test_wait_processor_is_started_and_stopped_with_application_lifespan() -> None:
    app_source = open("src/api/presentation/rest/app.py", encoding="utf-8").read()
    di_source = open("src/api/application/di.py", encoding="utf-8").read()

    assert "AgentWaitConditionProcessor" in di_source
    assert "MvpResearchAutoResumer" in di_source
    assert "wait_condition_processor.start()" in app_source
    assert "wait_condition_processor.stop()" in app_source


def test_wait_processor_resolves_from_application_container() -> None:
    script = """
import asyncio
from api.application.agent_wait_conditions import AgentWaitConditionProcessor
from api.application.container import create_container
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
