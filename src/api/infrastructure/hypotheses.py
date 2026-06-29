"""Storage adapter for research hypothesis candidates."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.dialects.postgresql import insert

from api.application.hypotheses import HypothesisCandidate, StoredHypothesis
from api.infrastructure.adapters.orm import (
    research_hypotheses,
    research_hypothesis_evidence,
)


class HypothesisStore:
    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

    async def upsert_candidate(self, candidate: HypothesisCandidate) -> StoredHypothesis:
        now = datetime.now(timezone.utc)
        statement = insert(research_hypotheses).values(
            id=uuid4(),
            program_id=candidate.program_id,
            hypothesis_type=candidate.hypothesis_type,
            hypothesis_fingerprint=candidate.hypothesis_fingerprint,
            status=candidate.status,
            state_version=1,
            priority_score=max(0, min(int(candidate.priority_score), 100)),
            confidence=max(0.0, min(float(candidate.confidence), 1.0)),
            severity_guess=candidate.severity_guess,
            safety_level=candidate.safety_level,
            score_version=candidate.score_version,
            inputs_hash=candidate.inputs_hash,
            source_signal_fingerprints=list(candidate.source_signal_fingerprints),
            first_seen=now,
            last_seen=now,
            updated_at=now,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[
                "program_id",
                "hypothesis_type",
                "hypothesis_fingerprint",
            ],
            set_={
                "status": candidate.status,
                "priority_score": max(0, min(int(candidate.priority_score), 100)),
                "confidence": max(0.0, min(float(candidate.confidence), 1.0)),
                "severity_guess": candidate.severity_guess,
                "safety_level": candidate.safety_level,
                "score_version": candidate.score_version,
                "inputs_hash": candidate.inputs_hash,
                "source_signal_fingerprints": list(candidate.source_signal_fingerprints),
                "last_seen": now,
                "updated_at": now,
            },
        ).returning(research_hypotheses.c.id)

        async with self.session_factory() as session:
            result = await session.execute(statement)
            hypothesis_id = result.scalar_one()
            for evidence in candidate.evidence:
                await session.execute(
                    insert(research_hypothesis_evidence)
                    .values(
                        id=uuid4(),
                        hypothesis_id=hypothesis_id,
                        ref_type=evidence.ref_type,
                        ref_id=evidence.ref_id,
                        field_path=evidence.field_path,
                        role=evidence.role,
                        claim_type=evidence.claim_type,
                        claim=evidence.claim,
                        evidence_fingerprint=evidence.fingerprint,
                        safe_excerpt=evidence.safe_excerpt,
                        safe_excerpt_truncated=False,
                        safe_excerpt_hash=None,
                        evidence_source=evidence.evidence_source,
                        normalized_content_hash=None,
                        sanitized_content_hash=None,
                        sanitizer_version=evidence.sanitizer_version,
                        redaction_policy_version=evidence.redaction_policy_version,
                        sensitivity_level=evidence.sensitivity_level,
                        redaction_rules_triggered=[],
                        safe_for_search=evidence.safe_for_search,
                        safe_for_embedding=evidence.safe_for_embedding,
                        safe_for_llm=evidence.safe_for_llm,
                    )
                    .on_conflict_do_update(
                        index_elements=["hypothesis_id", "evidence_fingerprint"],
                        set_={
                            "claim": evidence.claim,
                            "safe_excerpt": evidence.safe_excerpt,
                            "safe_for_search": evidence.safe_for_search,
                            "safe_for_embedding": evidence.safe_for_embedding,
                            "safe_for_llm": evidence.safe_for_llm,
                        },
                    )
                )
            await session.commit()

        return StoredHypothesis(
            hypothesis_id=hypothesis_id,
            program_id=candidate.program_id,
            hypothesis_type=candidate.hypothesis_type,
            status=candidate.status,
            priority_score=max(0, min(int(candidate.priority_score), 100)),
            confidence=max(0.0, min(float(candidate.confidence), 1.0)),
            evidence_count=len(candidate.evidence),
        )
