from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

PackType = Literal["observation", "asset", "cluster", "change"]
RefRole = Literal["primary", "supporting", "context", "contradicting"]


@dataclass(frozen=True)
class Subject:
    type: str
    id: str | None
    url: str | None
    method: str | None
    host: str | None
    path: str | None
    status_code: int | None
    content_type: str | None
    title: str | None


@dataclass(frozen=True)
class EvidenceRef:
    id: str
    ref_type: str
    ref_id: str
    field_path: str
    claim_type: str
    role: RefRole
    safe_excerpt: str | None
    safe_for_llm: bool
    safe_for_search: bool


@dataclass(frozen=True)
class PackSafety:
    safe_for_llm: bool
    safe_for_embedding: bool
    sanitizer_version: str
    redaction_policy_version: str


@dataclass(frozen=True)
class EvidencePack:
    pack_id: str
    pack_type: PackType
    program_id: str
    subject: Subject
    safe_features: dict[str, Any]
    evidence_refs: list[EvidenceRef]
    safety: PackSafety

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
