"""Deterministic evidence-pack assembly helpers for Workbench retrieval.

This module deliberately avoids request-time tool execution, OpenSearch network
reads, prompt assembly, or database writes. It ranks and filters already-loaded
entity memory, graph context, and safe references.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import re
from typing import Any


async def assemble_evidence_pack_payload(
    *,
    program_id: Any,
    lens: Any,
    selected_entities: list[str],
    query: str | None,
    temporal_scope: dict[str, Any],
    load_graph_context: Any,
    load_entity_profile: Any,
    load_entity_memory: Any,
    not_found_exceptions: tuple[type[BaseException], ...],
    boundary: dict[str, Any],
) -> dict[str, Any]:
    """Build a WorkbenchEvidencePack-compatible payload.

    The application service owns persistence/use-case routing. This helper owns
    retrieval assembly mechanics: redaction, temporal filtering, deterministic
    ranking, evidence ref de-duplication, and graph-context summaries.
    """
    selected = _dedupe_texts(selected_entities, limit=20)
    safe_query = _redact_text(query) if query else None
    terms = _query_terms(safe_query)
    scope = _temporal_scope(temporal_scope)
    graph_context = await _load_graph_context(
        selected_entities=selected,
        load_graph_context=load_graph_context,
    )

    fragments: list[dict[str, Any]] = []
    evidence_refs: list[dict[str, Any]] = []
    entity_summaries: list[dict[str, Any]] = []
    for entity_key in selected:
        profile = await _load_optional(
            load_entity_profile,
            entity_key,
            not_found_exceptions=not_found_exceptions,
        )
        memory = await _load_optional(
            load_entity_memory,
            entity_key,
            not_found_exceptions=not_found_exceptions,
        )
        entity_summaries.append(_entity_pack_summary(entity_key, profile, memory))
        if memory is None:
            continue
        filtered = _filter_fragments_by_scope(memory.fragments, scope)
        fragments.extend(_with_entity(fragment, entity_key) for fragment in filtered)
        evidence_refs.extend(memory.evidence_refs)
        if profile is not None:
            evidence_refs.extend(profile.evidence_refs)

    ranked_context = _rank_context_fragments(
        fragments=fragments,
        query_terms=terms,
        selected_entities=selected,
        limit=50,
    )
    evidence_refs.extend(_evidence_refs_from_context(ranked_context))
    return {
        "program_id": program_id,
        "lens": lens,
        "selected_entities": selected,
        "query": safe_query,
        "query_terms": terms,
        "temporal_scope": scope,
        "entity_summaries": entity_summaries,
        "evidence_refs": _dedupe_refs(evidence_refs),
        "fragments": [item["fragment"] for item in ranked_context],
        "ranked_context": ranked_context,
        "search_projection_refs": _search_projection_refs(ranked_context, graph_context),
        "graph_context": graph_context,
        "graph_context_summary": _graph_context_summary(graph_context, selected),
        "boundary": {
            **boundary,
            "query_decomposition": "deterministic_terms_only",
            "ranking": "deterministic_local_score",
            "opensearch_lookup": "not_performed",
            "prompt_blob": "forbidden",
            "summary_is_truth": False,
        },
    }


async def _load_graph_context(*, selected_entities: list[str], load_graph_context: Any) -> Any:
    if not selected_entities:
        return None
    return await load_graph_context(selected_entities[0])


async def _load_optional(
    loader: Any,
    entity_key: str,
    *,
    not_found_exceptions: tuple[type[BaseException], ...],
) -> Any:
    try:
        return await loader(entity_key)
    except not_found_exceptions:
        return None


_SECRET_KEY_RE = re.compile(r"(authorization|cookie|token|api[_-]?key|access[_-]?token|password|secret)", re.IGNORECASE)
_BEARER_RE = re.compile(r"(?i)authorization\s*:\s*bearer\s+[^\s,;]+")
_ASSIGNMENT_SECRET_RE = re.compile(r"(?i)\b(token|api[_-]?key|access[_-]?token|password|secret)=([^\s,;&]+)")
_WORD_RE = re.compile(r"[a-zA-Z0-9_./:-]{2,}")


def _dedupe_texts(values: list[str], *, limit: int) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
        if len(result) >= limit:
            break
    return result


def _query_terms(query: str | None) -> list[str]:
    if not query:
        return []
    terms: list[str] = []
    seen: set[str] = set()
    for term in _WORD_RE.findall(query.lower()):
        if _SECRET_KEY_RE.search(term):
            continue
        if term not in seen:
            seen.add(term)
            terms.append(term)
        if len(terms) >= 12:
            break
    return terms


def _temporal_scope(raw: dict[str, Any]) -> dict[str, Any]:
    if not raw:
        return {"applied": False}
    start = _first_datetime(raw, ("start_at", "start", "from", "since", "after", "created_after"))
    end = _first_datetime(raw, ("end_at", "end", "to", "until", "before", "created_before"))
    ignored = sorted(str(key) for key in raw if key not in {
        "start_at", "start", "from", "since", "after", "created_after",
        "end_at", "end", "to", "until", "before", "created_before",
    })
    return {
        "applied": bool(start or end),
        "start_at": start.isoformat() if start else None,
        "end_at": end.isoformat() if end else None,
        "ignored_keys": ignored,
    }


def _first_datetime(raw: dict[str, Any], keys: tuple[str, ...]) -> datetime | None:
    for key in keys:
        if key in raw:
            parsed = _parse_datetime(raw.get(key))
            if parsed is not None:
                return parsed
    return None


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _with_entity(fragment: dict[str, Any], entity_key: str) -> dict[str, Any]:
    safe = _safe_value(fragment)
    if not isinstance(safe, dict):
        return {"entity_key": entity_key, "value": safe}
    return {"entity_key": entity_key, **safe} if "entity_key" not in safe else safe


def _filter_fragments_by_scope(fragments: list[dict[str, Any]], scope: dict[str, Any]) -> list[dict[str, Any]]:
    if not scope.get("applied"):
        return [_safe_value(fragment) for fragment in fragments if isinstance(_safe_value(fragment), dict)]
    start = _parse_datetime(scope.get("start_at"))
    end = _parse_datetime(scope.get("end_at"))
    result: list[dict[str, Any]] = []
    for fragment in fragments:
        safe = _safe_value(fragment)
        if not isinstance(safe, dict):
            continue
        timestamp = _fragment_datetime(safe)
        if timestamp is None:
            result.append(safe)
            continue
        if start and timestamp < start:
            continue
        if end and timestamp > end:
            continue
        result.append(safe)
    return result


def _fragment_datetime(fragment: dict[str, Any]) -> datetime | None:
    for key in ("created_at", "finished_at", "observed_at", "last_seen_at", "timestamp"):
        parsed = _parse_datetime(fragment.get(key))
        if parsed is not None:
            return parsed
    return None


def _entity_pack_summary(
    entity_key: str,
    profile: WorkbenchEntityProfile | None,
    memory: WorkbenchEntityMemory | None,
) -> dict[str, Any]:
    return _safe_value({
        "entity_key": entity_key,
        "resolved": profile is not None or memory is not None,
        "node_type": (profile.profile or {}).get("node_type") if profile else None,
        "label": (profile.profile or {}).get("label") if profile else None,
        "evidence_ref_count": len(profile.evidence_refs) if profile else 0,
        "fragment_count": len(memory.fragments) if memory else 0,
        "summary_count": len(memory.summaries) if memory else 0,
        "memory_pointer_count": len(profile.memory_pointers) if profile else 0,
    })


def _rank_context_fragments(
    *,
    fragments: list[dict[str, Any]],
    query_terms: list[str],
    selected_entities: list[str],
    limit: int,
) -> list[dict[str, Any]]:
    scored = []
    for index, fragment in enumerate(fragments):
        score, reasons = _context_score(fragment, query_terms, selected_entities)
        scored.append((score, index, fragment, reasons))
    scored.sort(key=lambda item: (-item[0], item[1]))
    ranked: list[dict[str, Any]] = []
    for rank, (score, _, fragment, reasons) in enumerate(scored[:limit], start=1):
        ranked.append({
            "rank": rank,
            "score": round(score, 4),
            "reasons": reasons,
            "entity_key": fragment.get("entity_key"),
            "fragment": _safe_value(fragment),
            "evidence_refs": _fragment_evidence_refs(fragment),
        })
    return ranked


def _context_score(fragment: dict[str, Any], query_terms: list[str], selected_entities: list[str]) -> tuple[float, list[str]]:
    score = 1.0
    reasons = ["selected_entity_memory"]
    text = _json_text(fragment).lower()
    matches = [term for term in query_terms if term in text]
    if matches:
        score += len(matches) * 2.0
        reasons.append("query_term_match")
    entity_key = str(fragment.get("entity_key") or "")
    if entity_key in selected_entities:
        score += 2.0
        reasons.append("selected_entity_exact")
    delta_score = min(_fragment_delta_total(fragment), 10) / 2
    if delta_score:
        score += delta_score
        reasons.append("delta_signal")
    info_gain = _nested_number(fragment, ("score", "information_gain"))
    if info_gain:
        score += min(float(info_gain), 10.0) / 2
        reasons.append("information_gain")
    if _fragment_evidence_refs(fragment):
        score += 0.5
        reasons.append("evidence_ref")
    return score, reasons


def _fragment_delta_total(fragment: dict[str, Any]) -> int:
    delta = fragment.get("delta")
    if not isinstance(delta, dict):
        return 0
    total = 0
    for value in delta.values():
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            total += max(value, 0)
    return total


def _nested_number(fragment: dict[str, Any], path: tuple[str, ...]) -> float | None:
    current: Any = fragment
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return float(current) if isinstance(current, int | float) else None


def _fragment_evidence_refs(fragment: dict[str, Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for key, ref_type in (("outcome_id", "action_outcome"), ("run_id", "action_run"), ("artifact_id", "raw_artifact")):
        value = fragment.get(key)
        if value:
            refs.append({"type": ref_type, "id": str(value)})
    explicit = fragment.get("evidence_refs")
    if isinstance(explicit, list):
        refs.extend(ref for ref in explicit if isinstance(ref, dict))
    return _dedupe_refs(refs)


def _evidence_refs_from_context(ranked_context: list[dict[str, Any]]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for item in ranked_context:
        refs.extend(ref for ref in item.get("evidence_refs", []) if isinstance(ref, dict))
    return refs


def _graph_context_summary(graph: WorkbenchGraph | None, selected_entities: list[str]) -> dict[str, Any]:
    if graph is None:
        return {"available": False, "selected_entities_resolved": [], "missing_selected_entities": selected_entities}
    selected = [node for node in graph.nodes if node.entity_key in selected_entities]
    neighbor_ids = _neighbor_ids(graph, {node.id for node in selected})
    source_projections = sorted({edge.source_projection for edge in graph.edges})
    node_types: dict[str, int] = {}
    for node in graph.nodes:
        node_types[node.node_type] = node_types.get(node.node_type, 0) + 1
    return {
        "available": True,
        "lens": graph.lens.value,
        "seed": graph.seed,
        "node_count": len(graph.nodes),
        "edge_count": len(graph.edges),
        "selected_entities_resolved": [node.entity_key for node in selected],
        "missing_selected_entities": [entity for entity in selected_entities if entity not in {node.entity_key for node in selected}],
        "neighbor_count": len(neighbor_ids),
        "node_types": node_types,
        "source_projections": source_projections,
    }


def _neighbor_ids(graph: WorkbenchGraph, selected_ids: set[str]) -> set[str]:
    neighbors: set[str] = set()
    if not selected_ids:
        return neighbors
    for edge in graph.edges:
        if edge.source in selected_ids:
            neighbors.add(edge.target)
        if edge.target in selected_ids:
            neighbors.add(edge.source)
    return neighbors


def _search_projection_refs(ranked_context: list[dict[str, Any]], graph: WorkbenchGraph | None) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for item in ranked_context:
        fragment = item.get("fragment") or {}
        if not isinstance(fragment, dict):
            continue
        delta = fragment.get("delta")
        if isinstance(delta, dict) and int(delta.get("search_documents") or 0) > 0:
            refs.append({
                "type": "search_projection_delta",
                "run_id": str(fragment.get("run_id")),
                "new_search_documents_count": int(delta.get("search_documents") or 0),
            })
    if graph is not None:
        for node in graph.nodes:
            for ref in node.source_refs:
                if str(ref.get("type", "")).startswith("search"):
                    refs.append(ref)
    return _dedupe_refs(refs)



def _dedupe_refs(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[tuple[str, str], ...]] = set()
    result: list[dict[str, Any]] = []
    for ref in refs:
        safe = _safe_value(ref)
        if not isinstance(safe, dict):
            continue
        key = tuple(sorted((str(item_key), str(item_value)) for item_key, item_value in safe.items()))
        if key in seen:
            continue
        seen.add(key)
        result.append(safe)
    return result

def _json_text(value: Any) -> str:
    try:
        return json.dumps(_safe_value(value), sort_keys=True, default=str)
    except TypeError:
        return str(_safe_value(value))


def _safe_value(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            result[key_text] = "[redacted]" if _SECRET_KEY_RE.search(key_text) else _safe_value(item)
        return result
    if isinstance(value, list):
        return [_safe_value(item) for item in value]
    if isinstance(value, tuple):
        return [_safe_value(item) for item in value]
    if isinstance(value, str):
        return _redact_text(value)
    return value


def _redact_text(value: str) -> str:
    text = _BEARER_RE.sub("Authorization: Bearer [redacted]", value)
    return _ASSIGNMENT_SECRET_RE.sub(lambda match: f"{match.group(1)}=[redacted]", text)
