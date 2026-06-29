"""Deterministic selection policy for research hypotheses.

This module intentionally does not promote findings or execute tools. It turns
sanitized hypothesis search hits into bounded next-step decisions that a
LangGraph workflow can use to decide where human/critic/evidence effort should
be spent next.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Iterable
from typing import Any


TERMINAL_STATUSES = frozenset({"dismissed", "promoted"})
DUPLICATE_STATUS = "duplicate"
STALE_STATUS = "stale"
REVIEWING_STATUS = "reviewing"
NEEDS_VERIFICATION_STATUSES = frozenset({"new", "needs_verification", REVIEWING_STATUS})
ACTIVE_SAFETY_LEVELS = frozenset({"active", "safe_active", "sensitive"})
HIGH_IMPACT_SEVERITIES = frozenset({"medium", "high", "critical"})
SAFE_HIT_FIELDS = frozenset({
    "hypothesis_id",
    "program_id",
    "hypothesis_type",
    "status",
    "priority_score",
    "confidence",
    "severity_guess",
    "safety_level",
    "score_version",
    "source_signal_fingerprints",
    "evidence_count",
    "evidence_ref_types",
    "evidence_roles",
    "evidence_claim_types",
    "evidence_ref_ids",
    "safe_evidence_text",
    "last_seen",
    "updated_at",
})


@dataclass(frozen=True, slots=True)
class HypothesisSelectionDecision:
    hypothesis_id: str
    next_step: str
    priority_band: str
    reasons: tuple[str, ...]
    requires_human_review: bool = False
    safe_context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class HypothesisSelectionResult:
    decisions: tuple[HypothesisSelectionDecision, ...]


class HypothesisSelectionPolicy:
    """Ranks sanitized hypothesis hits and selects a bounded next step."""

    def __init__(self, *, max_items: int = 25) -> None:
        self.max_items = max(1, min(int(max_items), 100))

    def select(
        self,
        hypotheses: Iterable[dict[str, Any]],
    ) -> HypothesisSelectionResult:
        candidates = [self._safe_hit(item) for item in hypotheses]
        candidates.sort(
            key=lambda item: (
                -self._priority(item),
                -self._confidence(item),
                str(item.get("hypothesis_id") or ""),
            )
        )
        return HypothesisSelectionResult(
            decisions=tuple(
                self._decision(item)
                for item in candidates[: self.max_items]
                if item.get("hypothesis_id")
            )
        )

    def _decision(self, item: dict[str, Any]) -> HypothesisSelectionDecision:
        reasons: list[str] = []
        status = str(item.get("status") or "new")
        priority = self._priority(item)
        confidence = self._confidence(item)
        evidence_count = int(item.get("evidence_count") or 0)
        severity = str(item.get("severity_guess") or "info").lower()
        safety_level = str(item.get("safety_level") or "passive").lower()
        primary_evidence = "primary" in set(self._strings(item.get("evidence_roles")))
        requires_human_review = safety_level in ACTIVE_SAFETY_LEVELS

        if requires_human_review:
            reasons.append(f"safety_level:{safety_level}")

        if status in TERMINAL_STATUSES:
            reasons.append(f"terminal_status:{status}")
            return self._make_decision(
                item,
                next_step="defer",
                priority_band=self._priority_band(priority),
                reasons=reasons,
                requires_human_review=requires_human_review,
            )

        if status == DUPLICATE_STATUS:
            reasons.append("duplicate_status")
            return self._make_decision(
                item,
                next_step="duplicate_review",
                priority_band=self._priority_band(priority),
                reasons=reasons,
                requires_human_review=True,
            )

        if status == STALE_STATUS:
            reasons.append("stale_status")
            return self._make_decision(
                item,
                next_step="refresh_evidence",
                priority_band=self._priority_band(priority),
                reasons=reasons,
                requires_human_review=requires_human_review,
            )

        if evidence_count <= 0:
            reasons.append("missing_evidence")
            return self._make_decision(
                item,
                next_step="build_evidence",
                priority_band=self._priority_band(priority),
                reasons=reasons,
                requires_human_review=requires_human_review,
            )

        if not primary_evidence:
            reasons.append("missing_primary_evidence")
            return self._make_decision(
                item,
                next_step="build_evidence",
                priority_band=self._priority_band(priority),
                reasons=reasons,
                requires_human_review=requires_human_review,
            )

        if status == REVIEWING_STATUS and priority >= 85 and confidence >= 0.75 and evidence_count >= 3:
            reasons.extend(["reviewing_status", "high_priority", "high_confidence", "sufficient_evidence"])
            return self._make_decision(
                item,
                next_step="draft_report",
                priority_band="critical",
                reasons=reasons,
                requires_human_review=True,
            )

        if priority >= 70 and confidence >= 0.55:
            reasons.extend(["ready_for_critic", "priority_threshold_met"])
            if severity in HIGH_IMPACT_SEVERITIES:
                reasons.append(f"severity:{severity}")
            return self._make_decision(
                item,
                next_step="critic_review",
                priority_band=self._priority_band(priority),
                reasons=reasons,
                requires_human_review=requires_human_review,
            )

        if status in NEEDS_VERIFICATION_STATUSES:
            reasons.append("needs_more_signal")
            return self._make_decision(
                item,
                next_step="build_evidence",
                priority_band=self._priority_band(priority),
                reasons=reasons,
                requires_human_review=requires_human_review,
            )

        reasons.append(f"unhandled_status:{status}")
        return self._make_decision(
            item,
            next_step="defer",
            priority_band=self._priority_band(priority),
            reasons=reasons,
            requires_human_review=requires_human_review,
        )

    @staticmethod
    def _make_decision(
        item: dict[str, Any],
        *,
        next_step: str,
        priority_band: str,
        reasons: list[str],
        requires_human_review: bool,
    ) -> HypothesisSelectionDecision:
        return HypothesisSelectionDecision(
            hypothesis_id=str(item["hypothesis_id"]),
            next_step=next_step,
            priority_band=priority_band,
            reasons=tuple(reasons),
            requires_human_review=requires_human_review,
            safe_context={key: item[key] for key in SAFE_HIT_FIELDS if key in item},
        )

    @staticmethod
    def _safe_hit(item: dict[str, Any]) -> dict[str, Any]:
        return {key: item[key] for key in SAFE_HIT_FIELDS if key in item}

    @staticmethod
    def _priority(item: dict[str, Any]) -> int:
        return max(0, min(int(item.get("priority_score") or 0), 100))

    @staticmethod
    def _confidence(item: dict[str, Any]) -> float:
        return max(0.0, min(float(item.get("confidence") or 0.0), 1.0))

    @staticmethod
    def _priority_band(priority: int) -> str:
        if priority >= 85:
            return "critical"
        if priority >= 70:
            return "high"
        if priority >= 40:
            return "medium"
        return "low"

    @staticmethod
    def _strings(value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, str):
            return (value,)
        if isinstance(value, Iterable):
            return tuple(str(item) for item in value)
        return (str(value),)
