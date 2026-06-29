"""Deterministic hypothesis workflow contracts.

The builder consumes already-normalized result-set references and creates
manual-verification candidates. It stores pointers and sanitized claims only.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class HypothesisEvidenceRef:
    ref_type: str
    ref_id: str
    role: str
    claim_type: str
    claim: str
    field_path: str | None = None
    safe_excerpt: str | None = None
    evidence_source: str = "metadata_only"
    sanitizer_version: str = "metadata-only-v1"
    redaction_policy_version: str = "redaction-policy-v1"
    sensitivity_level: str = "metadata"
    safe_for_search: bool = False
    safe_for_embedding: bool = False
    safe_for_llm: bool = False

    @property
    def fingerprint(self) -> str:
        return _sha256(
            {
                "ref_type": self.ref_type,
                "ref_id": self.ref_id,
                "role": self.role,
                "claim_type": self.claim_type,
                "claim": self.claim,
                "field_path": self.field_path,
            }
        )


@dataclass(frozen=True, slots=True)
class HypothesisCandidate:
    program_id: UUID
    hypothesis_type: str
    evidence: tuple[HypothesisEvidenceRef, ...]
    status: str = "needs_verification"
    priority_score: int = 0
    confidence: float = 0.0
    severity_guess: str | None = "info"
    safety_level: str = "passive"
    score_version: str = "hypothesis-builder-v1"
    source_signal_fingerprints: tuple[str, ...] = field(default_factory=tuple)

    @property
    def hypothesis_fingerprint(self) -> str:
        return _sha256(
            {
                "program_id": str(self.program_id),
                "hypothesis_type": self.hypothesis_type,
                "evidence": [item.fingerprint for item in self.evidence],
            }
        )

    @property
    def inputs_hash(self) -> str:
        return _sha256(
            {
                "score_version": self.score_version,
                "evidence": [item.fingerprint for item in self.evidence],
                "source_signal_fingerprints": list(self.source_signal_fingerprints),
            }
        )


@dataclass(frozen=True, slots=True)
class StoredHypothesis:
    hypothesis_id: UUID
    program_id: UUID
    hypothesis_type: str
    status: str
    priority_score: int
    confidence: float
    evidence_count: int


@dataclass(frozen=True, slots=True)
class HypothesisBuildRequest:
    program_id: UUID
    result_key: str | None = None
    action_id: UUID | None = None
    campaign_id: UUID | None = None
    workflow_id: UUID | None = None
    workflow_run_id: UUID | None = None
    limit: int = 25


@dataclass(frozen=True, slots=True)
class HypothesisBuildResult:
    hypotheses: tuple[StoredHypothesis, ...]
    candidates: tuple[HypothesisCandidate, ...] = ()
    finding_ids: tuple[UUID, ...] = ()


class HypothesisRepository(Protocol):
    async def upsert_candidate(self, candidate: HypothesisCandidate) -> StoredHypothesis: ...


class HypothesisContextTools(Protocol):
    async def result_sets(self, **kwargs) -> dict[str, Any]: ...


class HypothesisBuilderWorkflow:
    def __init__(
        self,
        *,
        context_tools: HypothesisContextTools,
        hypothesis_store: HypothesisRepository,
    ) -> None:
        self.context_tools = context_tools
        self.hypothesis_store = hypothesis_store

    async def build_from_result_sets(
        self,
        request: HypothesisBuildRequest,
    ) -> HypothesisBuildResult:
        result = await self.context_tools.result_sets(
            program_id=request.program_id,
            result_key=request.result_key,
            action_id=request.action_id,
            campaign_id=request.campaign_id,
            workflow_id=request.workflow_id,
            workflow_run_id=request.workflow_run_id,
            limit=max(1, min(int(request.limit), 100)),
        )
        stored: list[StoredHypothesis] = []
        candidates: list[HypothesisCandidate] = []
        for item in result.get("items", ()):
            candidate = self._candidate_from_result_set(request.program_id, item)
            if candidate is None:
                continue
            candidates.append(candidate)
            stored.append(await self.hypothesis_store.upsert_candidate(candidate))
        return HypothesisBuildResult(
            hypotheses=tuple(stored),
            candidates=tuple(candidates),
        )

    def _candidate_from_result_set(
        self,
        program_id: UUID,
        item: dict[str, Any],
    ) -> HypothesisCandidate | None:
        evidence = self._evidence_from_result_set(item)
        if len(evidence) <= 1:
            return None
        evidence_refs = tuple(evidence)
        priority = min(100, 20 + (len(evidence_refs) * 5))
        confidence = min(0.85, 0.2 + (len(evidence_refs) * 0.05))
        return HypothesisCandidate(
            program_id=program_id,
            hypothesis_type=self._hypothesis_type(item),
            evidence=evidence_refs,
            priority_score=priority,
            confidence=confidence,
            severity_guess="info",
            source_signal_fingerprints=tuple(ref.fingerprint for ref in evidence_refs),
        )

    def _evidence_from_result_set(self, item: dict[str, Any]) -> list[HypothesisEvidenceRef]:
        result_key = str(item.get("result_key") or "")
        refs = [
            HypothesisEvidenceRef(
                ref_type="result_set",
                ref_id=result_key,
                role="context",
                claim_type="result_set_context",
                claim=f"Result set {result_key} contains surface signals for manual review.",
            )
        ]
        refs.extend(
            self._refs(
                ref_type="artifact",
                rows=item.get("artifact_refs", ()),
                claim_type="artifact_reference",
                claim="Artifact reference supports this manual-review candidate.",
            )
        )
        refs.extend(
            self._refs(
                ref_type="fact",
                rows=item.get("fact_refs", ()),
                claim_type="canonical_fact_reference",
                claim="Canonical fact reference supports this manual-review candidate.",
            )
        )
        refs.extend(
            self._refs(
                ref_type="search",
                rows=item.get("search_refs", ()),
                claim_type="search_reference",
                claim="Search projection reference supports this manual-review candidate.",
            )
        )
        refs.extend(
            self._refs(
                ref_type="graph",
                rows=item.get("graph_refs", ()),
                claim_type="graph_reference",
                claim="Graph reference supports this manual-review candidate.",
            )
        )
        return [ref for ref in refs if ref.ref_id]

    @staticmethod
    def _refs(
        *,
        ref_type: str,
        rows: Any,
        claim_type: str,
        claim: str,
    ) -> list[HypothesisEvidenceRef]:
        refs = []
        for row in rows or ():
            ref_id = _row_ref_id(row)
            if not ref_id:
                continue
            refs.append(
                HypothesisEvidenceRef(
                    ref_type=ref_type,
                    ref_id=ref_id,
                    role="supporting" if ref_type != "graph" else "primary",
                    claim_type=claim_type,
                    claim=claim,
                    field_path=_row_field_path(row),
                )
            )
        return refs

    @staticmethod
    def _hypothesis_type(item: dict[str, Any]) -> str:
        if item.get("graph_refs"):
            return "graph_surface_followup"
        if item.get("search_refs"):
            return "search_surface_followup"
        if item.get("artifact_refs"):
            return "artifact_surface_followup"
        return "surface_map_followup"


def _row_ref_id(row: Any) -> str:
    if not isinstance(row, dict):
        return str(row)
    for key in (
        "artifact_id",
        "fact_id",
        "search_id",
        "node_id",
        "edge_id",
        "id",
        "ref_id",
        "template",
    ):
        value = row.get(key)
        if value:
            return str(value)
    return ""


def _row_field_path(row: Any) -> str | None:
    if not isinstance(row, dict):
        return None
    value = row.get("field_path") or row.get("role") or row.get("template")
    return str(value) if value else None


def _sha256(value: dict[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
