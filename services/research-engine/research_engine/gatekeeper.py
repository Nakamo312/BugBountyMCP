from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, ClassVar

ALLOWED_HYPOTHESIS_TYPES = {
    "possible_exposed_api_docs",
    "possible_auth_surface",
    "possible_sensitive_admin_surface",
    "possible_schema_exposure",
}
ALLOWED_SAFETY_LEVELS = {"passive", "needs_manual_review"}
ALLOWED_NEXT_STEPS = {"manual_review", "passive_reindex", "request_triage"}
RAW_LIKE_SUMMARY_MARKERS = ("password=", "token=", "authorization:", "set-cookie:")


@dataclass(frozen=True)
class GatekeeperDecision:
    status: str
    output: dict[str, Any] | None = None
    reasons: tuple[str, ...] = ()

    ACCEPT: ClassVar[str] = "accept"
    ACCEPT_WITH_CHANGES: ClassVar[str] = "accept_with_changes"
    REJECT: ClassVar[str] = "reject"


def validate_generator_output(
    output: dict[str, Any],
    *,
    available_evidence_ref_ids: set[str],
) -> GatekeeperDecision:
    candidate = deepcopy(output)
    reasons: list[str] = []
    changed = False

    hypotheses = candidate.get("hypotheses")
    if not isinstance(hypotheses, list):
        return GatekeeperDecision(GatekeeperDecision.REJECT, reasons=("missing hypotheses list",))

    for hypothesis in hypotheses:
        if not isinstance(hypothesis, dict):
            return GatekeeperDecision(GatekeeperDecision.REJECT, reasons=("hypothesis is not an object",))

        hypothesis_type = hypothesis.get("hypothesis_type")
        if hypothesis_type not in ALLOWED_HYPOTHESIS_TYPES:
            reasons.append(f"unsupported hypothesis_type: {hypothesis_type}")

        safety_level = hypothesis.get("safety_level")
        if safety_level not in ALLOWED_SAFETY_LEVELS:
            reasons.append(f"unsupported safety_level: {safety_level}")

        summary = str(hypothesis.get("summary") or "")
        if _contains_raw_like_summary(summary):
            reasons.append("summary contains raw-like sensitive marker")

        observed_facts = hypothesis.get("observed_facts")
        if not isinstance(observed_facts, list) or not observed_facts:
            reasons.append("missing observed facts")
        else:
            for fact in observed_facts:
                fact_refs = fact.get("evidence_ref_ids") if isinstance(fact, dict) else None
                if not isinstance(fact_refs, list) or not fact_refs:
                    reasons.append("observed fact missing evidence refs")
                    continue
                unknown_refs = set(map(str, fact_refs)).difference(available_evidence_ref_ids)
                if unknown_refs:
                    reasons.append(f"unknown evidence refs: {','.join(sorted(unknown_refs))}")

        for step in hypothesis.get("safe_next_steps") or []:
            if not isinstance(step, dict) or step.get("action_type") not in ALLOWED_NEXT_STEPS:
                reasons.append(f"unsupported safe_next_step: {step.get('action_type') if isinstance(step, dict) else step}")

        if len(observed_facts or []) == 1 and float(hypothesis.get("confidence") or 0.0) > 0.7:
            hypothesis["confidence"] = 0.7
            changed = True

    if reasons:
        return GatekeeperDecision(GatekeeperDecision.REJECT, reasons=tuple(reasons))
    if changed:
        return GatekeeperDecision(GatekeeperDecision.ACCEPT_WITH_CHANGES, output=candidate)
    return GatekeeperDecision(GatekeeperDecision.ACCEPT, output=output)


def _contains_raw_like_summary(summary: str) -> bool:
    normalized = summary.lower()
    return any(marker in normalized for marker in RAW_LIKE_SUMMARY_MARKERS)
