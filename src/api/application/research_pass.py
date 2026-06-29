"""Research pass from normalized result sets to critic decisions and report drafts."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from api.application.hypotheses import (
    HypothesisBuildRequest,
    HypothesisBuildResult,
    HypothesisCandidate,
    StoredHypothesis,
)
from api.application.hypothesis_critic import CriticDecision
from api.application.report_drafts import ReportDraft


class HypothesisBuilder(Protocol):
    async def build_from_result_sets(
        self,
        request: HypothesisBuildRequest,
    ) -> HypothesisBuildResult: ...


class HypothesisCritic(Protocol):
    async def review(self, candidate: HypothesisCandidate) -> CriticDecision: ...


class ReportDraftBuilder(Protocol):
    def build(
        self,
        candidate: HypothesisCandidate,
        critic_decision: CriticDecision,
    ) -> ReportDraft: ...


@dataclass(frozen=True, slots=True)
class ResearchPassItem:
    hypothesis: StoredHypothesis
    critic: CriticDecision
    report_draft: ReportDraft


@dataclass(frozen=True, slots=True)
class ResearchPassSummary:
    status: str
    total_hypotheses: int
    accepted_by_critic: int
    needs_evidence: int
    rejected_by_critic: int
    drafts_ready: int
    blocked_drafts: int

    def as_safe_dict(self) -> dict[str, int | str]:
        return {
            "status": self.status,
            "total_hypotheses": self.total_hypotheses,
            "accepted_by_critic": self.accepted_by_critic,
            "needs_evidence": self.needs_evidence,
            "rejected_by_critic": self.rejected_by_critic,
            "drafts_ready": self.drafts_ready,
            "blocked_drafts": self.blocked_drafts,
        }


@dataclass(frozen=True, slots=True)
class ResearchPassResult:
    items: tuple[ResearchPassItem, ...]
    finding_ids: tuple[UUID, ...] = ()
    summary: ResearchPassSummary | None = None

    def safe_summary(self) -> dict[str, int | str]:
        return (self.summary or summarize_research_pass(self.items)).as_safe_dict()


class ResearchPass:
    def __init__(
        self,
        *,
        hypothesis_builder: HypothesisBuilder,
        hypothesis_critic: HypothesisCritic,
        report_builder: ReportDraftBuilder,
    ) -> None:
        self.hypothesis_builder = hypothesis_builder
        self.hypothesis_critic = hypothesis_critic
        self.report_builder = report_builder

    async def run(self, request: HypothesisBuildRequest) -> ResearchPassResult:
        build_result = await self.hypothesis_builder.build_from_result_sets(request)
        items = []
        for stored, candidate in zip(
            build_result.hypotheses,
            build_result.candidates,
            strict=True,
        ):
            decision = await self.hypothesis_critic.review(candidate)
            report_draft = self.report_builder.build(candidate, decision)
            items.append(
                ResearchPassItem(
                    hypothesis=stored,
                    critic=decision,
                    report_draft=report_draft,
                )
            )
        result_items = tuple(items)
        return ResearchPassResult(
            items=result_items,
            summary=summarize_research_pass(result_items),
        )


def summarize_research_pass(
    items: tuple[ResearchPassItem, ...],
) -> ResearchPassSummary:
    total = len(items)
    accepted = sum(1 for item in items if item.critic.status == "accepted")
    needs_evidence = sum(
        1 for item in items if item.critic.status == "needs_evidence"
    )
    rejected = sum(1 for item in items if item.critic.status == "rejected")
    drafts_ready = sum(1 for item in items if item.report_draft.status == "draft")
    blocked_drafts = sum(
        1 for item in items if item.report_draft.status.startswith("blocked_")
    )
    return ResearchPassSummary(
        status=_research_pass_status(
            total=total,
            drafts_ready=drafts_ready,
            needs_evidence=needs_evidence,
            rejected=rejected,
            accepted=accepted,
        ),
        total_hypotheses=total,
        accepted_by_critic=accepted,
        needs_evidence=needs_evidence,
        rejected_by_critic=rejected,
        drafts_ready=drafts_ready,
        blocked_drafts=blocked_drafts,
    )


def _research_pass_status(
    *,
    total: int,
    drafts_ready: int,
    needs_evidence: int,
    rejected: int,
    accepted: int,
) -> str:
    if total == 0:
        return "empty"
    if drafts_ready:
        return "drafts_ready"
    if needs_evidence:
        return "needs_evidence"
    if rejected == total:
        return "rejected"
    if accepted:
        return "reviewed"
    return "reviewed"
