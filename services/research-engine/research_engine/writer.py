from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any

SCORE_VERSION = "semantic-score-v1"
SANITIZER_VERSION = "research-sanitizer-v1"
REDACTION_POLICY_VERSION = "redaction-policy-v1"
SAFE_EXCERPT_LIMIT = 512


@dataclass(frozen=True)
class ResearchRows:
    hypotheses: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    score_history: list[dict[str, Any]]
    events: list[dict[str, Any]]


def build_research_rows(
    *,
    program_id: str,
    producer_run_id: str,
    pack_id: str,
    pack_evidence_refs: list[dict[str, Any]],
    generator_output: dict[str, Any],
) -> ResearchRows:
    _require_text(program_id, "program_id")
    _require_text(producer_run_id, "producer_run_id")
    _require_text(pack_id, "pack_id")

    evidence_by_id = {str(ref["id"]): ref for ref in pack_evidence_refs if ref.get("id")}
    hypotheses: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []
    score_rows: list[dict[str, Any]] = []
    event_rows: list[dict[str, Any]] = []

    for hypothesis in generator_output.get("hypotheses") or []:
        observed_facts = hypothesis.get("observed_facts") or []
        claim_types = sorted({str(fact.get("claim_type")) for fact in observed_facts if fact.get("claim_type")})
        hypothesis_fingerprint = _hypothesis_fingerprint(
            program_id=program_id,
            hypothesis_type=str(hypothesis["hypothesis_type"]),
            pack_id=pack_id,
            claim_types=claim_types,
        )
        inputs_hash = _hash_json(
            {
                "pack_id": pack_id,
                "evidence_ref_ids": sorted(evidence_by_id),
                "claim_types": claim_types,
            }
        )
        hypothesis_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"research:{program_id}:{hypothesis_fingerprint}"))
        confidence = float(hypothesis.get("confidence") or 0.0)
        priority_score = _priority_score(confidence, str(hypothesis.get("severity_guess") or ""))

        hypotheses.append(
            {
                "id": hypothesis_id,
                "program_id": program_id,
                "hypothesis_type": hypothesis["hypothesis_type"],
                "hypothesis_fingerprint": hypothesis_fingerprint,
                "status": "new",
                "state_version": 1,
                "priority_score": priority_score,
                "confidence": confidence,
                "severity_guess": hypothesis.get("severity_guess"),
                "safety_level": hypothesis.get("safety_level", "passive"),
                "score_version": SCORE_VERSION,
                "inputs_hash": inputs_hash,
                "source_signal_fingerprints": [],
                "summary": hypothesis.get("summary"),
                "safe_next_steps": hypothesis.get("safe_next_steps") or [],
            }
        )

        for fact in observed_facts:
            for evidence_ref_id in fact.get("evidence_ref_ids") or []:
                evidence_ref = evidence_by_id.get(str(evidence_ref_id))
                if evidence_ref is None:
                    raise ValueError(f"unknown evidence ref: {evidence_ref_id}")
                evidence_rows.append(
                    _evidence_row(
                        hypothesis_id=hypothesis_id,
                        pack_id=pack_id,
                        fact=fact,
                        evidence_ref=evidence_ref,
                    )
                )

        score_rows.append(
            {
                "hypothesis_id": hypothesis_id,
                "score_version": SCORE_VERSION,
                "priority_score": priority_score,
                "confidence": confidence,
                "severity_guess": hypothesis.get("severity_guess"),
                "safety_level": hypothesis.get("safety_level", "passive"),
                "inputs_hash": inputs_hash,
                "factors_json": {
                    "producer_run_id": producer_run_id,
                    "pack_id": pack_id,
                    "claim_types": claim_types,
                    "observed_fact_count": len(observed_facts),
                },
            }
        )
        event_rows.append(
            {
                "hypothesis_id": hypothesis_id,
                "event_type": "hypothesis_proposed",
                "aggregate_version": 1,
                "actor": "research-engine",
                "reason": "semantic hypothesis proposed by generator output",
                "payload_json": {
                    "producer_run_id": producer_run_id,
                    "pack_id": pack_id,
                    "hypothesis_type": hypothesis.get("hypothesis_type"),
                },
            }
        )

    return ResearchRows(
        hypotheses=hypotheses,
        evidence=evidence_rows,
        score_history=score_rows,
        events=event_rows,
    )


def _evidence_row(*, hypothesis_id: str, pack_id: str, fact: dict[str, Any], evidence_ref: dict[str, Any]) -> dict[str, Any]:
    safe_excerpt = evidence_ref.get("safe_excerpt")
    safe_excerpt_text = None if safe_excerpt is None else str(safe_excerpt)
    safe_excerpt_hash = _sha256(safe_excerpt_text) if safe_excerpt_text is not None else None
    truncated = False
    if safe_excerpt_text is not None and len(safe_excerpt_text) > SAFE_EXCERPT_LIMIT:
        safe_excerpt_text = safe_excerpt_text[:SAFE_EXCERPT_LIMIT]
        truncated = True

    evidence_fingerprint = _hash_json(
        {
            "pack_id": pack_id,
            "evidence_ref_id": evidence_ref.get("id"),
            "ref_type": evidence_ref.get("ref_type"),
            "ref_id": evidence_ref.get("ref_id"),
            "field_path": evidence_ref.get("field_path"),
            "claim_type": fact.get("claim_type"),
            "claim": fact.get("claim"),
        }
    )
    return {
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"research-evidence:{hypothesis_id}:{evidence_fingerprint}")),
        "hypothesis_id": hypothesis_id,
        "ref_type": evidence_ref.get("ref_type", "unknown"),
        "ref_id": str(evidence_ref.get("ref_id", "")),
        "field_path": evidence_ref.get("field_path"),
        "role": evidence_ref.get("role", "primary"),
        "claim_type": fact.get("claim_type"),
        "claim": fact.get("claim"),
        "evidence_fingerprint": evidence_fingerprint,
        "safe_excerpt": safe_excerpt_text,
        "safe_excerpt_truncated": truncated,
        "safe_excerpt_hash": safe_excerpt_hash,
        "evidence_source": evidence_ref.get("evidence_source") or ("sanitizer" if safe_excerpt_text else "metadata_only"),
        "normalized_content_hash": evidence_ref.get("normalized_content_hash"),
        "sanitized_content_hash": evidence_ref.get("sanitized_content_hash") or safe_excerpt_hash,
        "sanitizer_version": evidence_ref.get("sanitizer_version", SANITIZER_VERSION),
        "redaction_policy_version": evidence_ref.get("redaction_policy_version", REDACTION_POLICY_VERSION),
        "sensitivity_level": evidence_ref.get("sensitivity_level", "public"),
        "redaction_rules_triggered": evidence_ref.get("redaction_rules_triggered", []),
        "safe_for_search": evidence_ref.get("safe_for_search", safe_excerpt_text is not None),
        "safe_for_embedding": evidence_ref.get("safe_for_embedding", True),
        "safe_for_llm": evidence_ref.get("safe_for_llm", True),
    }


def _hypothesis_fingerprint(*, program_id: str, hypothesis_type: str, pack_id: str, claim_types: list[str]) -> str:
    return _hash_json(
        {
            "program_id": program_id,
            "hypothesis_type": hypothesis_type,
            "pack_id": pack_id,
            "claim_types": claim_types,
        }
    )


def _priority_score(confidence: float, severity_guess: str) -> int:
    severity_bonus = {
        "critical": 25,
        "high": 18,
        "medium": 10,
        "low": 4,
        "info": 0,
    }.get(severity_guess.lower(), 0)
    return max(0, min(100, int(confidence * 70) + severity_bonus))


def _require_text(value: str, name: str) -> None:
    if not value:
        raise ValueError(f"{name} is required")


def _hash_json(value: dict[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return _sha256(payload)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
