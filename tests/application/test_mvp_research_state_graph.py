from __future__ import annotations

from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver

from api.application.hypotheses import HypothesisBuildRequest, StoredHypothesis
from api.application.hypothesis_critic import CriticDecision
from api.application.mvp_research_state_graph import MvpResearchStateGraph
from api.application.mvp_research_readiness import ResearchReadinessDecision
from api.application.mvp_research_workflow import MvpResearchItem, MvpResearchResult
from api.application.projections import ProjectionKey
from api.application.report_drafts import ReportDraft


class RecordingResearchWorkflow:
    def __init__(self, result: MvpResearchResult) -> None:
        self.result = result
        self.requests = []

    async def run(self, request: HypothesisBuildRequest) -> MvpResearchResult:
        self.requests.append(request)
        return self.result


class SequencedReadinessGate:
    def __init__(self, decisions) -> None:
        self.decisions = list(decisions)
        self.calls = []

    async def evaluate(self, request, *, required_projections):
        self.calls.append((request, required_projections))
        return self.decisions.pop(0)


async def test_compiled_research_graph_persists_pointer_only_state() -> None:
    program_id = uuid4()
    workflow_id = uuid4()
    workflow_run_id = uuid4()
    hypothesis_id = uuid4()
    research = RecordingResearchWorkflow(
        MvpResearchResult(
            items=(
                MvpResearchItem(
                    hypothesis=StoredHypothesis(
                        hypothesis_id=hypothesis_id,
                        program_id=program_id,
                        hypothesis_type="graph_surface_followup",
                        status="needs_verification",
                        priority_score=40,
                        confidence=0.45,
                        evidence_count=2,
                    ),
                    critic=CriticDecision(
                        status="accepted",
                        checks=(),
                        can_draft_report=True,
                    ),
                    report_draft=ReportDraft(
                        status="draft",
                        title="Sensitive title must not enter graph state",
                        body="Authorization: Bearer must-not-enter-state",
                        evidence_chain=(),
                        redactions=("authorization",),
                    ),
                ),
            ),
        )
    )
    graph = MvpResearchStateGraph(
        research_workflow=research,
        checkpointer=InMemorySaver(),
    )
    request = HypothesisBuildRequest(
        program_id=program_id,
        result_key="surface:admin",
        workflow_id=workflow_id,
        workflow_run_id=workflow_run_id,
    )

    result = await graph.ainvoke(request, thread_id=str(workflow_run_id))
    snapshot = await graph.aget_state(thread_id=str(workflow_run_id))
    resumed = await graph.aresume(thread_id=str(workflow_run_id))

    assert research.requests == [request]
    assert result["hypothesis_ids"] == [str(hypothesis_id)]
    assert result["critic_statuses"] == ["accepted"]
    assert result["draft_statuses"] == ["draft"]
    assert result["finding_ids"] == []
    assert snapshot.values == result
    assert resumed == result
    assert research.requests == [request]
    assert "body" not in result
    assert "evidence" not in result
    assert "must-not-enter-state" not in repr(result)


def test_research_graph_is_compiled_and_wired_without_execution_authority() -> None:
    graph_source = open(
        "src/api/application/mvp_research_state_graph.py",
        encoding="utf-8",
    ).read()
    di_source = open("src/api/application/di.py", encoding="utf-8").read()
    requirements = open("requirements.txt", encoding="utf-8").read()

    assert "StateGraph" in graph_source
    assert ".compile(" in graph_source
    assert "get_mvp_research_state_graph" in di_source
    assert "langgraph==" in requirements
    for forbidden in (
        "RabbitMQ",
        "EventBus",
        "runner",
        "subprocess",
        "request_action",
        "raw_artifact",
    ):
        assert forbidden not in graph_source


async def test_research_graph_interrupts_until_projection_and_result_sets_are_ready() -> None:
    program_id = uuid4()
    workflow_run_id = uuid4()
    wait_condition_id = uuid4()
    research = RecordingResearchWorkflow(MvpResearchResult(items=()))
    gate = SequencedReadinessGate(
        [
            ResearchReadinessDecision(
                ready=False,
                reason="projections_not_ready",
                wait_condition_id=wait_condition_id,
                payload={"lagging": [{"projection_name": "http-observations"}]},
            ),
            ResearchReadinessDecision(
                ready=True,
                reason="research_inputs_ready",
                result_set_keys=("surface:admin",),
            ),
        ]
    )
    graph = MvpResearchStateGraph(
        research_workflow=research,
        readiness_gate=gate,
        checkpointer=InMemorySaver(),
    )
    request = HypothesisBuildRequest(
        program_id=program_id,
        workflow_run_id=workflow_run_id,
        result_key="surface:admin",
    )
    required = (ProjectionKey("opensearch", "http-observations"),)

    waiting = await graph.ainvoke(
        request,
        thread_id=str(workflow_run_id),
        required_projections=required,
    )
    waiting_state = await graph.aget_state(thread_id=str(workflow_run_id))

    assert "__interrupt__" in waiting
    assert waiting_state.values["readiness_status"] == "waiting"
    assert waiting_state.values["wait_condition_id"] == str(wait_condition_id)
    assert waiting_state.values["wait_reason"] == "projections_not_ready"
    assert research.requests == []

    completed = await graph.aresume(thread_id=str(workflow_run_id))

    assert completed["readiness_status"] == "ready"
    assert completed["result_set_keys"] == ["surface:admin"]
    assert completed["hypothesis_ids"] == []
    assert research.requests == [request]
    assert len(gate.calls) == 2
    assert gate.calls[0][1] == required
