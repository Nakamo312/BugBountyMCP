from __future__ import annotations

from uuid import uuid4

from api.application.hypotheses import HypothesisCandidate, HypothesisEvidenceRef
from api.application.hypothesis_critic import HypothesisCriticWorkflow


class RecordingScopeReader:
    def __init__(self, allowed: bool) -> None:
        self.allowed = allowed
        self.calls = []

    async def evidence_refs_in_scope(self, *, program_id, evidence_refs):
        self.calls.append((program_id, evidence_refs))
        return {evidence.ref_id: self.allowed for evidence in evidence_refs}


def candidate(*evidence: HypothesisEvidenceRef, severity_guess: str | None = "info"):
    return HypothesisCandidate(
        program_id=uuid4(),
        hypothesis_type="graph_surface_followup",
        evidence=tuple(evidence),
        priority_score=30,
        confidence=0.35,
        severity_guess=severity_guess,
    )


def evidence(
    *,
    ref_type: str = "graph",
    ref_id: str = "Endpoint:/admin",
    role: str = "primary",
    claim_type: str = "graph_reference",
    sensitivity_level: str = "metadata",
    evidence_source: str = "metadata_only",
    safe_for_llm: bool = False,
) -> HypothesisEvidenceRef:
    return HypothesisEvidenceRef(
        ref_type=ref_type,
        ref_id=ref_id,
        role=role,
        claim_type=claim_type,
        claim="Manual verification candidate.",
        sensitivity_level=sensitivity_level,
        evidence_source=evidence_source,
        safe_for_llm=safe_for_llm,
    )


async def test_critic_blocks_candidate_with_missing_evidence() -> None:
    critic = HypothesisCriticWorkflow(scope_reader=RecordingScopeReader(True))

    decision = await critic.review(candidate())

    assert decision.status == "needs_evidence"
    assert decision.can_draft_report is False
    assert "missing_evidence" in {check.check_id for check in decision.checks}


async def test_critic_rejects_out_of_scope_evidence_refs() -> None:
    critic = HypothesisCriticWorkflow(scope_reader=RecordingScopeReader(False))

    decision = await critic.review(candidate(evidence()))

    assert decision.status == "rejected"
    assert decision.can_draft_report is False
    assert "scope" in {check.category for check in decision.checks}


async def test_critic_rejects_unsafe_artifact_content() -> None:
    critic = HypothesisCriticWorkflow(scope_reader=RecordingScopeReader(True))

    decision = await critic.review(
        candidate(
            evidence(
                ref_type="artifact",
                ref_id="artifact-1",
                evidence_source="sanitizer",
                sensitivity_level="credential",
                safe_for_llm=False,
            )
        )
    )

    assert decision.status == "rejected"
    assert decision.can_draft_report is False
    assert "unsafe_artifact" in {check.check_id for check in decision.checks}


async def test_critic_requires_impact_evidence_for_high_severity_guess() -> None:
    critic = HypothesisCriticWorkflow(scope_reader=RecordingScopeReader(True))

    decision = await critic.review(candidate(evidence(), severity_guess="high"))

    assert decision.status == "needs_evidence"
    assert decision.can_draft_report is False
    assert "unsupported_impact" in {check.check_id for check in decision.checks}


async def test_critic_accepts_candidate_with_scope_evidence_and_impact_support() -> None:
    scope = RecordingScopeReader(True)
    critic = HypothesisCriticWorkflow(scope_reader=scope)

    decision = await critic.review(
        candidate(
            evidence(),
            evidence(
                ref_type="fact",
                ref_id="impact:admin-panel",
                role="supporting",
                claim_type="impact_reference",
            ),
            severity_guess="high",
        )
    )

    assert decision.status == "accepted"
    assert decision.can_draft_report is True
    assert scope.calls


def test_hypothesis_critic_does_not_import_finding_or_execution_surfaces() -> None:
    source = open("src/api/application/hypothesis_critic.py", encoding="utf-8").read()

    for forbidden in (
        "Finding",
        "findings",
        "RabbitMQ",
        "EventBus",
        "runner",
        "subprocess",
        "request_action",
    ):
        assert forbidden not in source
