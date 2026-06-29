from __future__ import annotations

from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver

from api.application.hypotheses import HypothesisBuildRequest, StoredHypothesis
from api.application.hypothesis_critic import CriticDecision
from api.application.research_control_graph import ResearchControlGraph
from api.application.research_readiness import (
    ResearchReadinessDecision,
    ResearchReadinessReason,
)
from api.application.research_pass import ResearchPassItem, ResearchPassResult
from api.application.projections import ProjectionKey
from api.application.report_drafts import ReportDraft


class RecordingResearchWorkflow:
    def __init__(self, result: ResearchPassResult) -> None:
        self.result = result
        self.requests = []

    async def run(self, request: HypothesisBuildRequest) -> ResearchPassResult:
        self.requests.append(request)
        return self.result


class SequencedReadinessGate:
    def __init__(self, decisions) -> None:
        self.decisions = list(decisions)
        self.calls = []

    async def evaluate(self, request, *, required_projections):
        self.calls.append((request, required_projections))
        return self.decisions.pop(0)


class RecordingHypothesisSelector:
    def __init__(self, decisions) -> None:
        self.decisions = decisions
        self.calls = []

    async def select_hypotheses(self, **kwargs):
        self.calls.append(kwargs)
        return {"decisions": self.decisions}


async def test_compiled_research_graph_persists_pointer_only_state() -> None:
    program_id = uuid4()
    workflow_id = uuid4()
    workflow_run_id = uuid4()
    hypothesis_id = uuid4()
    research = RecordingResearchWorkflow(
        ResearchPassResult(
            items=(
                ResearchPassItem(
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
    graph = ResearchControlGraph(
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
    assert result["research_pass_status"] == "drafts_ready"
    assert result["research_pass_summary"] == {
        "status": "drafts_ready",
        "total_hypotheses": 1,
        "accepted_by_critic": 1,
        "needs_evidence": 0,
        "rejected_by_critic": 0,
        "drafts_ready": 1,
        "blocked_drafts": 0,
    }
    assert snapshot.values == result
    assert resumed == result
    assert research.requests == [request]
    assert "body" not in result
    assert "evidence" not in result
    assert "must-not-enter-state" not in repr(result)


def test_research_graph_is_compiled_and_wired_without_execution_authority() -> None:
    graph_source = open(
        "src/api/application/research_control_graph.py",
        encoding="utf-8",
    ).read()
    di_source = open("src/api/application/di.py", encoding="utf-8").read()
    requirements = open("requirements.txt", encoding="utf-8").read()

    assert "StateGraph" in graph_source
    assert ".compile(" in graph_source
    assert "get_research_control_graph" in di_source
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
    research = RecordingResearchWorkflow(ResearchPassResult(items=()))
    gate = SequencedReadinessGate(
        [
            ResearchReadinessDecision(
                ready=False,
                reason="projections_not_ready",
                wait_condition_id=wait_condition_id,
                reason_code=ResearchReadinessReason.PROJECTION_LAGGING,
                wait_condition_type="projections_ready",
                payload={"lagging": [{"projection_name": "http-observations"}]},
            ),
            ResearchReadinessDecision(
                ready=True,
                reason="research_inputs_ready",
                result_set_keys=("surface:admin",),
            ),
        ]
    )
    graph = ResearchControlGraph(
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
    assert (
        waiting_state.values["wait_reason_code"]
        == ResearchReadinessReason.PROJECTION_LAGGING
    )
    assert waiting_state.values["wait_condition_type"] == "projections_ready"
    assert research.requests == []

    completed = await graph.aresume(thread_id=str(workflow_run_id))

    assert completed["readiness_status"] == "ready"
    assert completed["result_set_keys"] == ["surface:admin"]
    assert completed["hypothesis_ids"] == []
    assert completed["research_pass_status"] == "empty"
    assert completed["research_pass_summary"]["total_hypotheses"] == 0
    assert research.requests == [request]
    assert len(gate.calls) == 2
    assert gate.calls[0][1] == required


async def test_research_graph_records_selected_next_steps_without_text_context() -> None:
    program_id = uuid4()
    workflow_run_id = uuid4()
    hypothesis_id = uuid4()
    research = RecordingResearchWorkflow(
        ResearchPassResult(
            items=(
                ResearchPassItem(
                    hypothesis=StoredHypothesis(
                        hypothesis_id=hypothesis_id,
                        program_id=program_id,
                        hypothesis_type="tenant_boundary",
                        status="needs_verification",
                        priority_score=90,
                        confidence=0.8,
                        evidence_count=3,
                    ),
                    critic=CriticDecision(
                        status="accepted",
                        checks=(),
                        can_draft_report=True,
                    ),
                    report_draft=ReportDraft(
                        status="draft",
                        title="Pointer-only draft",
                        body="must not enter graph state",
                        evidence_chain=(),
                        redactions=(),
                    ),
                ),
            ),
        )
    )
    selector = RecordingHypothesisSelector(
        [
            {
                "hypothesis_id": str(hypothesis_id),
                "next_step": "critic_review",
                "priority_band": "critical",
                "reasons": ["ready_for_critic"],
                "requires_human_review": True,
                "safe_context": {
                    "hypothesis_type": "tenant_boundary",
                    "status": "needs_verification",
                    "evidence_count": 3,
                    "safe_evidence_text": "safe text still must not enter control state",
                },
            }
        ]
    )
    graph = ResearchControlGraph(
        research_workflow=research,
        hypothesis_selector=selector,
        checkpointer=InMemorySaver(),
    )
    request = HypothesisBuildRequest(
        program_id=program_id,
        workflow_run_id=workflow_run_id,
        limit=7,
    )

    result = await graph.ainvoke(request, thread_id=str(workflow_run_id))

    assert selector.calls == [
        {
            "program_id": program_id,
            "status": ("new", "needs_verification", "reviewing", "stale"),
            "min_priority_score": 0,
            "limit": 7,
        }
    ]
    assert result["selection_status"] == "selected"
    assert result["selected_hypothesis_steps"] == [
        {
            "hypothesis_id": str(hypothesis_id),
            "next_step": "critic_review",
            "priority_band": "critical",
            "requires_human_review": True,
            "reasons": ["ready_for_critic"],
            "hypothesis_type": "tenant_boundary",
            "status": "needs_verification",
            "evidence_count": 3,
        }
    ]
    assert "safe text still must not enter control state" not in repr(result)
    assert "must not enter graph state" not in repr(result)
