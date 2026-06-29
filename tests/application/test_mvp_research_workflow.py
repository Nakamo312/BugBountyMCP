from __future__ import annotations

from uuid import uuid4

from api.application.hypotheses import (
    HypothesisBuildRequest,
    HypothesisBuildResult,
    HypothesisCandidate,
    HypothesisEvidenceRef,
    StoredHypothesis,
)
from api.application.hypothesis_critic import CriticDecision
from api.application.mvp_research_workflow import MvpResearchWorkflow
from api.application.report_drafts import ReportDraft


class RecordingBuilder:
    def __init__(
        self,
        *,
        candidate: HypothesisCandidate,
        stored: StoredHypothesis,
    ) -> None:
        self.candidate = candidate
        self.stored = stored
        self.requests = []

    async def build_from_result_sets(
        self,
        request: HypothesisBuildRequest,
    ) -> HypothesisBuildResult:
        self.requests.append(request)
        return HypothesisBuildResult(
            hypotheses=(self.stored,),
            candidates=(self.candidate,),
        )


class RecordingCritic:
    def __init__(self) -> None:
        self.candidates = []

    async def review(self, candidate: HypothesisCandidate) -> CriticDecision:
        self.candidates.append(candidate)
        return CriticDecision(status="accepted", checks=(), can_draft_report=True)


class RecordingReportBuilder:
    def __init__(self) -> None:
        self.calls = []

    def build(
        self,
        candidate: HypothesisCandidate,
        critic_decision: CriticDecision,
    ) -> ReportDraft:
        self.calls.append((candidate, critic_decision))
        return ReportDraft(
            status="draft",
            title="Draft",
            body="Evidence-backed draft",
            evidence_chain=(),
            redactions=(),
        )


async def test_mvp_research_workflow_builds_reviews_and_drafts_without_findings() -> None:
    program_id = uuid4()
    hypothesis_id = uuid4()
    candidate = HypothesisCandidate(
        program_id=program_id,
        hypothesis_type="graph_surface_followup",
        evidence=(
            HypothesisEvidenceRef(
                ref_type="graph",
                ref_id="Endpoint:/admin",
                role="primary",
                claim_type="graph_reference",
                claim="Hidden endpoint needs manual verification.",
            ),
        ),
    )
    stored = StoredHypothesis(
        hypothesis_id=hypothesis_id,
        program_id=program_id,
        hypothesis_type=candidate.hypothesis_type,
        status=candidate.status,
        priority_score=candidate.priority_score,
        confidence=candidate.confidence,
        evidence_count=1,
    )
    builder = RecordingBuilder(candidate=candidate, stored=stored)
    critic = RecordingCritic()
    report_builder = RecordingReportBuilder()
    workflow = MvpResearchWorkflow(
        hypothesis_builder=builder,
        hypothesis_critic=critic,
        report_builder=report_builder,
    )
    request = HypothesisBuildRequest(program_id=program_id)

    result = await workflow.run(request)

    assert builder.requests == [request]
    assert critic.candidates == [candidate]
    assert report_builder.calls[0][0] is candidate
    assert len(result.items) == 1
    assert result.items[0].hypothesis.hypothesis_id == hypothesis_id
    assert result.items[0].critic.status == "accepted"
    assert result.items[0].report_draft.status == "draft"
    assert result.finding_ids == ()


async def test_mvp_research_workflow_returns_empty_result_when_builder_has_no_candidates() -> None:
    program_id = uuid4()

    class EmptyBuilder:
        async def build_from_result_sets(self, request):
            return HypothesisBuildResult(hypotheses=(), candidates=())

    workflow = MvpResearchWorkflow(
        hypothesis_builder=EmptyBuilder(),
        hypothesis_critic=RecordingCritic(),
        report_builder=RecordingReportBuilder(),
    )

    result = await workflow.run(HypothesisBuildRequest(program_id=program_id))

    assert result.items == ()
    assert result.finding_ids == ()


def test_mvp_research_workflow_is_wired_through_di_without_execution_authority() -> None:
    workflow_source = open(
        "src/api/application/mvp_research_workflow.py",
        encoding="utf-8",
    ).read()
    di_source = open("src/api/application/di.py", encoding="utf-8").read()

    assert "get_mvp_research_workflow" in di_source
    for forbidden in (
        "RabbitMQ",
        "EventBus",
        "runner",
        "subprocess",
        "request_action",
        "findings",
    ):
        assert forbidden not in workflow_source
