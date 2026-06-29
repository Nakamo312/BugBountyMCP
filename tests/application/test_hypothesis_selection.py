from __future__ import annotations

from api.application.hypothesis_selection import HypothesisSelectionPolicy


def test_selection_policy_sorts_and_sends_ready_hypothesis_to_critic() -> None:
    result = HypothesisSelectionPolicy().select(
        [
            {
                "hypothesis_id": "low",
                "program_id": "program-1",
                "status": "needs_verification",
                "priority_score": 35,
                "confidence": 0.4,
                "evidence_count": 2,
                "evidence_roles": ["primary"],
            },
            {
                "hypothesis_id": "ready",
                "program_id": "program-1",
                "status": "needs_verification",
                "priority_score": 82,
                "confidence": 0.71,
                "severity_guess": "medium",
                "evidence_count": 2,
                "evidence_roles": ["primary", "supporting"],
            },
        ]
    )

    assert [item.hypothesis_id for item in result.decisions] == ["ready", "low"]
    assert result.decisions[0].next_step == "critic_review"
    assert result.decisions[0].priority_band == "high"
    assert "ready_for_critic" in result.decisions[0].reasons


def test_selection_policy_requires_evidence_before_critic() -> None:
    result = HypothesisSelectionPolicy().select(
        [
            {
                "hypothesis_id": "no-primary",
                "status": "needs_verification",
                "priority_score": 90,
                "confidence": 0.9,
                "evidence_count": 3,
                "evidence_roles": ["supporting"],
            },
            {
                "hypothesis_id": "empty",
                "status": "needs_verification",
                "priority_score": 90,
                "confidence": 0.9,
                "evidence_count": 0,
                "evidence_roles": [],
            },
        ]
    )

    by_id = {item.hypothesis_id: item for item in result.decisions}
    assert by_id["no-primary"].next_step == "build_evidence"
    assert by_id["empty"].next_step == "build_evidence"
    assert "missing_primary_evidence" in by_id["no-primary"].reasons
    assert "missing_evidence" in by_id["empty"].reasons


def test_selection_policy_only_drafts_reviewing_high_confidence_items() -> None:
    result = HypothesisSelectionPolicy().select(
        [
            {
                "hypothesis_id": "draftable",
                "status": "reviewing",
                "priority_score": 95,
                "confidence": 0.8,
                "evidence_count": 3,
                "evidence_roles": ["primary", "supporting"],
            }
        ]
    )

    decision = result.decisions[0]
    assert decision.next_step == "draft_report"
    assert decision.requires_human_review is True
    assert "sufficient_evidence" in decision.reasons


def test_selection_policy_treats_active_safety_as_human_review_required() -> None:
    result = HypothesisSelectionPolicy().select(
        [
            {
                "hypothesis_id": "active-hypothesis",
                "status": "needs_verification",
                "priority_score": 75,
                "confidence": 0.7,
                "evidence_count": 2,
                "evidence_roles": ["primary"],
                "safety_level": "safe_active",
            }
        ]
    )

    decision = result.decisions[0]
    assert decision.next_step == "critic_review"
    assert decision.requires_human_review is True
    assert "safety_level:safe_active" in decision.reasons


def test_selection_policy_defers_terminal_and_routes_duplicate_or_stale() -> None:
    result = HypothesisSelectionPolicy().select(
        [
            {"hypothesis_id": "done", "status": "promoted", "priority_score": 90},
            {"hypothesis_id": "dupe", "status": "duplicate", "priority_score": 80},
            {"hypothesis_id": "old", "status": "stale", "priority_score": 70},
        ]
    )

    by_id = {item.hypothesis_id: item for item in result.decisions}
    assert by_id["done"].next_step == "defer"
    assert by_id["dupe"].next_step == "duplicate_review"
    assert by_id["dupe"].requires_human_review is True
    assert by_id["old"].next_step == "refresh_evidence"


def test_selection_policy_strips_raw_fields_from_safe_context() -> None:
    result = HypothesisSelectionPolicy().select(
        [
            {
                "hypothesis_id": "safe",
                "program_id": "program-1",
                "status": "needs_verification",
                "priority_score": 90,
                "confidence": 0.8,
                "evidence_count": 2,
                "evidence_roles": ["primary"],
                "safe_evidence_text": ["safe excerpt"],
                "raw_content": "must not leak",
                "claim": "must not leak",
                "_score": 1.0,
            }
        ]
    )

    context = result.decisions[0].safe_context
    assert context["safe_evidence_text"] == ["safe excerpt"]
    assert "raw_content" not in context
    assert "claim" not in context
    assert "_score" not in context
