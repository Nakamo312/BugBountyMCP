"""Bounded context summarization helpers for agent task role nodes."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ContextRefSummary:
    total: int
    counts_by_kind: dict[str, int]
    refs_by_kind: dict[str, tuple[dict[str, Any], ...]]
    thread_message_count: int = 0
    recent_outcome_count: int = 0
    pending_proposal_count: int = 0
    surface_counts: dict[str, int] = field(default_factory=dict)
    thread_messages: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    recent_outcomes: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    pending_proposals: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    recent_http: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    recent_javascript: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    @classmethod
    def from_context(cls, context: dict[str, Any]) -> "ContextRefSummary":
        refs_by_kind: dict[str, list[dict[str, Any]]] = {}
        for item in context.get("context_refs") or ():
            if not isinstance(item, dict):
                continue
            safe = _safe_ref(item)
            kind = _ref_kind(safe)
            refs_by_kind.setdefault(kind, []).append(safe)
        frozen_refs = {key: tuple(values) for key, values in refs_by_kind.items()}
        counts = {key: len(values) for key, values in frozen_refs.items()}
        surface_summary = context.get("surface_summary") if isinstance(context.get("surface_summary"), dict) else {}
        raw_surface_counts = surface_summary.get("counts") if isinstance(surface_summary.get("counts"), dict) else {}
        surface_counts = {
            str(key): int(value or 0)
            for key, value in raw_surface_counts.items()
            if isinstance(value, (int, float))
        }
        thread_messages = _bounded_context_dicts(context.get("thread_messages"), limit=8)
        recent_outcomes = _bounded_context_dicts(context.get("recent_outcomes"), limit=8)
        pending_proposals = _bounded_context_dicts(context.get("pending_proposals"), limit=5)
        recent_http = _bounded_context_dicts(surface_summary.get("recent_http"), limit=5)
        recent_javascript = _bounded_context_dicts(surface_summary.get("recent_javascript"), limit=5)
        return cls(
            total=sum(counts.values()),
            counts_by_kind=counts,
            refs_by_kind=frozen_refs,
            thread_message_count=len(thread_messages),
            recent_outcome_count=len(recent_outcomes),
            pending_proposal_count=len(pending_proposals),
            surface_counts=surface_counts,
            thread_messages=tuple(thread_messages),
            recent_outcomes=tuple(recent_outcomes),
            pending_proposals=tuple(pending_proposals),
            recent_http=tuple(recent_http),
            recent_javascript=tuple(recent_javascript),
        )

    def human_line(self) -> str:
        parts: list[str] = []
        if self.total:
            ref_parts = [f"{kind}: {count}" for kind, count in sorted(self.counts_by_kind.items())[:8]]
            parts.append("refs: " + ", ".join(ref_parts))
        if self.thread_message_count:
            parts.append(f"thread messages: {self.thread_message_count}")
        if self.recent_outcome_count:
            parts.append(f"recent outcomes: {self.recent_outcome_count}")
        if self.pending_proposal_count:
            parts.append(f"pending proposals: {self.pending_proposal_count}")
        if self.surface_counts:
            compact_counts = ", ".join(
                f"{key}: {value}" for key, value in sorted(self.surface_counts.items())[:4]
            )
            parts.append("surface: " + compact_counts)
        if not parts:
            return "Контекст не приложен. Буду отвечать только по тексту задачи и не буду выдумывать найденное."
        return "Получил компактный безопасный контекст: " + "; ".join(parts) + "."

    def as_metadata(self) -> dict[str, Any]:
        return {
            "context_ref_count": self.total,
            "counts_by_kind": dict(sorted(self.counts_by_kind.items())),
            "thread_message_count": self.thread_message_count,
            "recent_outcome_count": self.recent_outcome_count,
            "pending_proposal_count": self.pending_proposal_count,
            "surface_counts": dict(sorted(self.surface_counts.items())),
            "recent_http_count": len(self.recent_http),
            "recent_javascript_count": len(self.recent_javascript),
            "strongest_outcome": _outcome_metadata(self.strongest_outcome()),
            "top_pending_proposal": _proposal_metadata(self.top_pending_proposal()),
        }

    def strongest_outcome(self) -> dict[str, Any] | None:
        if not self.recent_outcomes:
            return None
        return max(
            self.recent_outcomes,
            key=lambda item: float(item.get("information_gain_score") or 0.0),
        )

    def top_pending_proposal(self) -> dict[str, Any] | None:
        if not self.pending_proposals:
            return None
        return max(
            self.pending_proposals,
            key=lambda item: float(item.get("utility_score") or 0.0),
        )

def _safe_ref(item: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in list(item.items())[:30]:
        text_key = str(key)[:120]
        safe[text_key] = _safe_value(value)
    return safe


def _safe_value(value: Any) -> Any:
    if isinstance(value, str):
        return value[:1000]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(key)[:120]: _safe_value(item) for key, item in list(value.items())[:20]}
    if isinstance(value, list):
        return [_safe_value(item) for item in value[:20]]
    return str(value)[:1000]


def _ref_kind(item: dict[str, Any]) -> str:
    for key in ("kind", "type", "ref_kind", "source"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().lower().replace("_", "-")[:80]
    return "context"


def _bounded_context_dicts(items: Any, *, limit: int) -> list[dict[str, Any]]:
    if not items:
        return []
    bounded: list[dict[str, Any]] = []
    for item in list(items)[: max(0, limit)]:
        if isinstance(item, dict):
            bounded.append(_safe_ref(item))
    return bounded


def _dedupe_ref_tuple(items: list[dict[str, Any]], *, limit: int) -> tuple[dict[str, Any], ...]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        if not item:
            continue
        key = f"{item.get('kind')}:{item.get('id') or item.get('url') or item.get('referenced_url') or item}"
        if key in seen:
            continue
        seen.add(key)
        result.append(_safe_ref(item))
        if len(result) >= limit:
            break
    return tuple(result)


def _safe_short(value: Any, *, limit: int = 80) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())[: max(0, limit)]


def _outcome_metadata(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not item:
        return None
    return {
        "outcome_id": item.get("outcome_id"),
        "capability_id": item.get("capability_id"),
        "profile_id": item.get("profile_id"),
        "information_gain_score": float(item.get("information_gain_score") or 0.0),
    }


def _proposal_metadata(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not item:
        return None
    return {
        "proposal_id": item.get("proposal_id"),
        "capability_id": item.get("capability_id"),
        "profile_id": item.get("profile_id"),
        "utility_score": float(item.get("utility_score") or 0.0),
        "sample_count": int(item.get("sample_count") or 0),
    }
