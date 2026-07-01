from __future__ import annotations

from collections import Counter
from dataclasses import replace
from typing import Any, Iterable

from .models import SurfaceNodeDraft


def dedupe_surface_node_drafts(drafts: Iterable[SurfaceNodeDraft]) -> list[SurfaceNodeDraft]:
    """Deduplicate drafts by node_fingerprint while preserving aggregate counts."""

    grouped: dict[str, SurfaceNodeDraft] = {}
    counts: Counter[str] = Counter()
    exemplar_refs: dict[str, list[str]] = {}
    for draft in drafts:
        key = draft.node_fingerprint
        counts[key] += 1
        if draft.ref_id:
            refs = exemplar_refs.setdefault(key, [])
            if draft.ref_id not in refs and len(refs) < 10:
                refs.append(draft.ref_id)
        if key not in grouped:
            grouped[key] = _with_count(draft, observation_count=1, exemplar_refs=exemplar_refs.get(key, []))
            continue
        existing = grouped[key]
        grouped[key] = _merge_node_drafts(
            existing,
            draft,
            observation_count=counts[key],
            exemplar_refs=exemplar_refs.get(key, []),
        )
    return sorted(grouped.values(), key=lambda node: (node.node_type, node.node_fingerprint))


def _merge_node_drafts(
    left: SurfaceNodeDraft,
    right: SurfaceNodeDraft,
    *,
    observation_count: int,
    exemplar_refs: list[str],
) -> SurfaceNodeDraft:
    first_seen = _min_seen(left.first_seen, right.first_seen)
    last_seen = _max_seen(left.last_seen, right.last_seen)
    return _with_count(
        replace(
            left,
            first_seen=first_seen,
            last_seen=last_seen,
            ref_id=left.ref_id or right.ref_id,
            ref_type=left.ref_type or right.ref_type,
        ),
        observation_count=observation_count,
        exemplar_refs=exemplar_refs,
    )


def _with_count(
    draft: SurfaceNodeDraft,
    *,
    observation_count: int,
    exemplar_refs: list[str],
) -> SurfaceNodeDraft:
    features = dict(draft.features_json)
    features["surface_node"] = {
        "observation_count": observation_count,
        "exemplar_ref_ids": list(exemplar_refs),
    }
    return replace(draft, features_json=features)


def _min_seen(left: Any, right: Any) -> Any:
    values = [value for value in (left, right) if value is not None]
    return min(values) if values else None


def _max_seen(left: Any, right: Any) -> Any:
    values = [value for value in (left, right) if value is not None]
    return max(values) if values else None
