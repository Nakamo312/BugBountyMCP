from __future__ import annotations

from uuid import uuid4

from api.application.hypotheses import HypothesisCandidate, HypothesisEvidenceRef
from api.application.hypothesis_critic import CriticCheck, CriticDecision
from api.application.report_drafts import ReportDraftBuilderWorkflow


def accepted_decision() -> CriticDecision:
    return CriticDecision(
        status="accepted",
        checks=(
            CriticCheck(
                check_id="evidence_present",
                category="evidence",
                passed=True,
                message="ok",
            ),
        ),
        can_draft_report=True,
    )


def candidate(*evidence: HypothesisEvidenceRef) -> HypothesisCandidate:
    return HypothesisCandidate(
        program_id=uuid4(),
        hypothesis_type="graph_surface_followup",
        evidence=tuple(evidence),
        priority_score=40,
        confidence=0.45,
        severity_guess="info",
    )


def evidence(
    *,
    ref_type: str = "graph",
    ref_id: str = "Endpoint:/admin",
    claim: str = "Hidden endpoint should be manually verified.",
    safe_excerpt: str | None = None,
) -> HypothesisEvidenceRef:
    return HypothesisEvidenceRef(
        ref_type=ref_type,
        ref_id=ref_id,
        role="primary",
        claim_type="graph_reference",
        claim=claim,
        safe_excerpt=safe_excerpt,
        safe_for_search=safe_excerpt is not None,
    )


def test_report_draft_links_evidence_chain() -> None:
    workflow = ReportDraftBuilderWorkflow()

    draft = workflow.build(
        candidate(
            evidence(ref_type="graph", ref_id="Endpoint:/admin"),
            evidence(ref_type="artifact", ref_id="artifact-1"),
        ),
        accepted_decision(),
    )

    assert draft.status == "draft"
    assert draft.final_status_allowed is False
    assert len(draft.evidence_chain) == 2
    assert draft.evidence_chain[0].ref_type == "graph"
    assert draft.evidence_chain[1].ref_id == "artifact-1"


def test_report_draft_redacts_tokens_cookies_and_authorization_values() -> None:
    workflow = ReportDraftBuilderWorkflow()

    draft = workflow.build(
        candidate(
            evidence(
                claim="Authorization: Bearer secret-token and Cookie: sessionid=abc123",
                safe_excerpt="token=secret-token; Set-Cookie: sessionid=abc123",
            )
        ),
        accepted_decision(),
    )

    text = draft.body
    assert "secret-token" not in text
    assert "abc123" not in text
    assert "[REDACTED_TOKEN]" in text
    assert "[REDACTED_COOKIE]" in text
    assert "secret-token" not in draft.evidence_chain[0].claim
    assert "abc123" not in draft.evidence_chain[0].claim


def test_report_draft_blocks_missing_evidence_from_final_status() -> None:
    workflow = ReportDraftBuilderWorkflow()
    decision = CriticDecision(
        status="needs_evidence",
        checks=(
            CriticCheck(
                check_id="missing_evidence",
                category="evidence",
                passed=False,
                message="missing",
            ),
        ),
    )

    draft = workflow.build(candidate(), decision)

    assert draft.status == "blocked_missing_evidence"
    assert draft.final_status_allowed is False
    assert draft.evidence_chain == ()


def test_report_draft_blocks_unaccepted_critic_decision() -> None:
    workflow = ReportDraftBuilderWorkflow()
    decision = CriticDecision(
        status="rejected",
        checks=(
            CriticCheck(
                check_id="unsafe_artifact",
                category="artifact_safety",
                passed=False,
                message="unsafe",
            ),
        ),
    )

    draft = workflow.build(candidate(evidence()), decision)

    assert draft.status == "blocked_by_critic"
    assert draft.final_status_allowed is False


def test_report_draft_builder_does_not_import_execution_surfaces() -> None:
    source = open("src/api/application/report_drafts.py", encoding="utf-8").read()

    for forbidden in (
        "RabbitMQ",
        "EventBus",
        "runner",
        "subprocess",
        "request_action",
    ):
        assert forbidden not in source
