"""Deterministic critic checks for hypothesis candidates."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from api.application.hypotheses import HypothesisCandidate, HypothesisEvidenceRef


@dataclass(frozen=True, slots=True)
class CriticCheck:
    check_id: str
    category: str
    passed: bool
    message: str


@dataclass(frozen=True, slots=True)
class CriticDecision:
    status: str
    checks: tuple[CriticCheck, ...]
    can_draft_report: bool = False


class EvidenceScopeReader(Protocol):
    async def evidence_refs_in_scope(
        self,
        *,
        program_id,
        evidence_refs: tuple[HypothesisEvidenceRef, ...],
    ) -> dict[str, bool]: ...


class ProgramBoundaryScopeReader:
    async def evidence_refs_in_scope(
        self,
        *,
        program_id,
        evidence_refs: tuple[HypothesisEvidenceRef, ...],
    ) -> dict[str, bool]:
        return {evidence.ref_id: True for evidence in evidence_refs}


class HypothesisCriticWorkflow:
    def __init__(self, *, scope_reader: EvidenceScopeReader) -> None:
        self.scope_reader = scope_reader

    async def review(self, candidate: HypothesisCandidate) -> CriticDecision:
        checks: list[CriticCheck] = []
        checks.append(self._missing_evidence_check(candidate))
        checks.extend(await self._scope_checks(candidate))
        checks.extend(self._unsafe_artifact_checks(candidate))
        checks.append(self._impact_check(candidate))
        return self._decision(tuple(checks))

    @staticmethod
    def _missing_evidence_check(candidate: HypothesisCandidate) -> CriticCheck:
        has_primary = any(item.role == "primary" for item in candidate.evidence)
        if candidate.evidence and has_primary:
            return CriticCheck(
                check_id="evidence_present",
                category="evidence",
                passed=True,
                message="Candidate has primary evidence references.",
            )
        return CriticCheck(
            check_id="missing_evidence",
            category="evidence",
            passed=False,
            message="Candidate needs at least one primary evidence reference.",
        )

    async def _scope_checks(self, candidate: HypothesisCandidate) -> tuple[CriticCheck, ...]:
        if not candidate.evidence:
            return ()
        decisions = await self.scope_reader.evidence_refs_in_scope(
            program_id=candidate.program_id,
            evidence_refs=candidate.evidence,
        )
        checks = []
        for evidence in candidate.evidence:
            allowed = bool(decisions.get(evidence.ref_id, False))
            checks.append(
                CriticCheck(
                    check_id=f"scope:{evidence.ref_id}",
                    category="scope",
                    passed=allowed,
                    message=(
                        "Evidence reference is inside the program boundary."
                        if allowed
                        else "Evidence reference is outside the program boundary."
                    ),
                )
            )
        return tuple(checks)

    @staticmethod
    def _unsafe_artifact_checks(candidate: HypothesisCandidate) -> tuple[CriticCheck, ...]:
        checks = []
        unsafe_levels = {"raw", "secret", "credential", "token", "pii"}
        for evidence in candidate.evidence:
            artifact_payload = evidence.ref_type == "artifact" and (
                evidence.evidence_source != "metadata_only" or evidence.safe_excerpt is not None
            )
            unsafe = evidence.sensitivity_level in unsafe_levels or (
                artifact_payload and not evidence.safe_for_llm
            )
            checks.append(
                CriticCheck(
                    check_id=(
                        "unsafe_artifact" if unsafe else f"artifact_safe:{evidence.ref_id}"
                    ),
                    category="artifact_safety",
                    passed=not unsafe,
                    message=(
                        "Evidence may expose unsafe artifact content."
                        if unsafe
                        else "Evidence reference is safe as bounded metadata."
                    ),
                )
            )
        return tuple(checks)

    @staticmethod
    def _impact_check(candidate: HypothesisCandidate) -> CriticCheck:
        high_signal = (candidate.severity_guess or "").lower() in {
            "critical",
            "high",
            "medium",
        }
        has_impact = any(
            item.claim_type in {"impact_reference", "business_impact", "exploitability"}
            for item in candidate.evidence
        )
        if not high_signal or has_impact:
            return CriticCheck(
                check_id="impact_supported",
                category="impact",
                passed=True,
                message="Impact is absent or supported by an evidence reference.",
            )
        return CriticCheck(
            check_id="unsupported_impact",
            category="impact",
            passed=False,
            message="Medium or higher severity guesses need impact evidence.",
        )

    @staticmethod
    def _decision(checks: tuple[CriticCheck, ...]) -> CriticDecision:
        failed = [check for check in checks if not check.passed]
        if not failed:
            return CriticDecision(
                status="accepted",
                checks=checks,
                can_draft_report=True,
            )
        if any(check.category in {"scope", "artifact_safety"} for check in failed):
            return CriticDecision(status="rejected", checks=checks)
        return CriticDecision(status="needs_evidence", checks=checks)
