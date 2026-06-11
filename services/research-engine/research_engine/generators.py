from __future__ import annotations

from typing import Any, Protocol

from research_engine.contracts import EvidencePack

STRUCTURED_OUTPUT_SCHEMA_VERSION = "semantic-hypothesis-output-v1"
FIXTURE_GENERATOR_PURPOSE = "contract-tests-only"

ALLOWED_OUTPUT_KEYS = {
    "hypotheses",
    "hypothesis_type",
    "confidence",
    "severity_guess",
    "safety_level",
    "summary",
    "observed_facts",
    "assumptions",
    "unknowns",
    "safe_next_steps",
}


class HypothesisGenerator(Protocol):
    def generate(self, packs: list[EvidencePack]) -> dict[str, Any]:
        ...


class FixtureHypothesisGenerator:
    """Deterministic contract-test fixture, not a production detector or rule engine."""

    def generate(self, packs: list[EvidencePack]) -> dict[str, Any]:
        hypotheses = []
        for pack in packs:
            if not _is_schema_like_api_docs(pack):
                continue
            evidence_ids = [ref.id for ref in pack.evidence_refs if ref.safe_for_llm]
            if not evidence_ids:
                continue
            hypotheses.append(_api_docs_hypothesis(pack, evidence_ids))

        return {
            "schema_version": STRUCTURED_OUTPUT_SCHEMA_VERSION,
            "hypotheses": hypotheses,
        }


def _is_schema_like_api_docs(pack: EvidencePack) -> bool:
    features = pack.safe_features
    json_keys = set(features.get("json_keys", []))
    title_tokens = set(features.get("title_tokens", []))
    path_tokens = set(features.get("path_tokens", []))
    shape_markers = set(features.get("shape_markers", []))

    schema_keys = {"openapi", "swagger", "paths", "components", "definitions"}
    schema_marker = "schema_like" in shape_markers or bool(schema_keys.intersection(json_keys))
    docs_marker = bool({"swagger", "api", "docs", "openapi"}.intersection(title_tokens | path_tokens | json_keys))
    return pack.pack_type == "observation" and schema_marker and docs_marker


def _api_docs_hypothesis(pack: EvidencePack, evidence_ids: list[str]) -> dict[str, Any]:
    facts = []
    if "schema_like" in set(pack.safe_features.get("shape_markers", [])) or set(pack.safe_features.get("json_keys", [])):
        facts.append(
            {
                "claim_type": "api_schema_marker_present",
                "claim": "Sanitized HTTP observation contains API schema markers.",
                "evidence_ref_ids": evidence_ids,
            }
        )
    if "swagger" in set(pack.safe_features.get("title_tokens", [])):
        facts.append(
            {
                "claim_type": "title_observed",
                "claim": "Sanitized HTTP observation title contains Swagger marker.",
                "evidence_ref_ids": evidence_ids,
            }
        )

    return {
        "hypothesis_type": "possible_exposed_api_docs",
        "confidence": 0.72,
        "severity_guess": "medium",
        "safety_level": "passive",
        "summary": "Endpoint appears to expose API documentation or schema metadata.",
        "observed_facts": facts,
        "assumptions": [
            "Schema-like markers may indicate intentionally published documentation.",
        ],
        "unknowns": [
            "Authentication and intended exposure are not known from passive evidence alone.",
        ],
        "safe_next_steps": [
            {
                "action_type": "manual_review",
                "description": "Review the referenced endpoint and program scope before any active probing.",
            }
        ],
        "evidence_pack_ids": [pack.pack_id],
    }
