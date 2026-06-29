"""Report draft builder for accepted hypothesis reviews."""
from __future__ import annotations

import re
from dataclasses import dataclass

from api.application.hypotheses import HypothesisCandidate, HypothesisEvidenceRef
from api.application.hypothesis_critic import CriticDecision


@dataclass(frozen=True, slots=True)
class EvidenceChainRef:
    ref_type: str
    ref_id: str
    role: str
    claim_type: str
    claim: str


@dataclass(frozen=True, slots=True)
class ReportDraft:
    status: str
    title: str
    body: str
    evidence_chain: tuple[EvidenceChainRef, ...]
    redactions: tuple[str, ...]
    final_status_allowed: bool = False


class ReportDraftBuilderWorkflow:
    def build(
        self,
        candidate: HypothesisCandidate,
        critic_decision: CriticDecision,
    ) -> ReportDraft:
        evidence_chain = tuple(self._evidence_chain(candidate.evidence))
        if not evidence_chain:
            return ReportDraft(
                status="blocked_missing_evidence",
                title="Blocked report draft",
                body="Report draft blocked: evidence chain is missing.",
                evidence_chain=(),
                redactions=(),
            )
        if critic_decision.status != "accepted" or not critic_decision.can_draft_report:
            return ReportDraft(
                status="blocked_by_critic",
                title="Blocked report draft",
                body=self._blocked_body(critic_decision),
                evidence_chain=evidence_chain,
                redactions=(),
            )

        body, redactions = self._body(candidate, evidence_chain)
        return ReportDraft(
            status="draft",
            title=self._title(candidate),
            body=body,
            evidence_chain=evidence_chain,
            redactions=tuple(redactions),
        )

    @staticmethod
    def _title(candidate: HypothesisCandidate) -> str:
        label = candidate.hypothesis_type.replace("_", " ").title()
        return f"Draft: {label}"

    @classmethod
    def _body(
        cls,
        candidate: HypothesisCandidate,
        evidence_chain: tuple[EvidenceChainRef, ...],
    ) -> tuple[str, list[str]]:
        lines = [
            f"Hypothesis type: {candidate.hypothesis_type}",
            f"Confidence: {candidate.confidence:.2f}",
            f"Priority: {candidate.priority_score}",
            "Evidence chain:",
        ]
        for index, evidence in enumerate(evidence_chain, start=1):
            lines.append(
                f"{index}. [{evidence.role}] {evidence.ref_type}:{evidence.ref_id} "
                f"({evidence.claim_type}) - {evidence.claim}"
            )
        raw_body = "\n".join(lines)
        return redact_report_text(raw_body)

    @staticmethod
    def _blocked_body(critic_decision: CriticDecision) -> str:
        failed = [check for check in critic_decision.checks if not check.passed]
        if not failed:
            return "Report draft blocked: critic did not accept this candidate."
        return "Report draft blocked:\n" + "\n".join(
            f"- {check.check_id}: {check.message}" for check in failed
        )

    @staticmethod
    def _evidence_chain(
        evidence_refs: tuple[HypothesisEvidenceRef, ...],
    ) -> list[EvidenceChainRef]:
        chain = []
        for evidence in evidence_refs:
            claim, _ = redact_report_text(
                "\n".join(
                    part for part in (evidence.claim, evidence.safe_excerpt) if part
                )
            )
            chain.append(
                EvidenceChainRef(
                    ref_type=evidence.ref_type,
                    ref_id=evidence.ref_id,
                    role=evidence.role,
                    claim_type=evidence.claim_type,
                    claim=claim,
                )
            )
        return chain


def redact_report_text(value: str) -> tuple[str, list[str]]:
    text = value
    redactions: list[str] = []
    patterns = (
        (
            "authorization",
            re.compile(r"(?i)(authorization\s*:\s*)(bearer\s+)?[^\s;,\n]+"),
            r"\1[REDACTED_TOKEN]",
        ),
        (
            "cookie",
            re.compile(r"(?i)((set-cookie|cookie)\s*:\s*)[^\n;]+"),
            r"\1[REDACTED_COOKIE]",
        ),
        (
            "token",
            re.compile(r"(?i)\b(token|api[_-]?key|sessionid)\s*=\s*[^\s;,\n]+"),
            r"\1=[REDACTED_TOKEN]",
        ),
    )
    for label, pattern, replacement in patterns:
        text, count = pattern.subn(replacement, text)
        if count:
            redactions.append(label)
    return text, redactions
