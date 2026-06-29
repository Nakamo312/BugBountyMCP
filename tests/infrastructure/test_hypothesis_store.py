from __future__ import annotations

from uuid import uuid4

from sqlalchemy.dialects import postgresql

from api.application.hypotheses import HypothesisCandidate, HypothesisEvidenceRef
from api.infrastructure.hypotheses import HypothesisStore


class FakeResult:
    def __init__(self, value) -> None:
        self.value = value

    def scalar_one(self):
        return self.value


class FakeSession:
    def __init__(self, hypothesis_id) -> None:
        self.hypothesis_id = hypothesis_id
        self.statements = []
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def execute(self, statement):
        self.statements.append(statement)
        return FakeResult(self.hypothesis_id)

    async def commit(self):
        self.committed = True


class FakeSessionFactory:
    def __init__(self, session: FakeSession) -> None:
        self.session = session

    def __call__(self):
        return self.session


async def test_hypothesis_store_upserts_hypothesis_and_evidence_without_findings() -> None:
    hypothesis_id = uuid4()
    session = FakeSession(hypothesis_id)
    store = HypothesisStore(FakeSessionFactory(session))
    candidate = HypothesisCandidate(
        program_id=uuid4(),
        hypothesis_type="graph_surface_followup",
        evidence=(
            HypothesisEvidenceRef(
                ref_type="graph",
                ref_id="Endpoint:/admin",
                role="primary",
                claim_type="hidden_endpoint",
                claim="Hidden endpoint should be manually verified.",
            ),
        ),
        priority_score=45,
        confidence=0.35,
        severity_guess="info",
    )

    record = await store.upsert_candidate(candidate)

    assert record.hypothesis_id == hypothesis_id
    assert record.status == "needs_verification"
    assert record.evidence_count == 1
    assert session.committed is True
    compiled = "\n".join(
        str(statement.compile(dialect=postgresql.dialect()))
        for statement in session.statements
    )
    assert "INSERT INTO research_hypotheses" in compiled
    assert "INSERT INTO research_hypothesis_evidence" in compiled
    assert "INSERT INTO findings" not in compiled


def test_hypothesis_store_source_does_not_touch_findings_table() -> None:
    source = open("src/api/infrastructure/hypotheses.py", encoding="utf-8").read()

    assert "research_hypotheses" in source
    assert "research_hypothesis_evidence" in source
    assert "findings" not in source
