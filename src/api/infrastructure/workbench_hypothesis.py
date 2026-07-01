"""Hypothesis lens builders for the dashboard workbench.

The hypothesis lens is a read-only projection over persisted research rows:
structural/research signals, hypothesis candidates, evidence, critic/event
history, score history, and proposal references. It must not promote
hypotheses to findings, create proposals, submit actions, run graph math, or
read raw artifact bodies.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from api.application.research.sanitizer import sanitize_json, sanitize_text
from api.application.workbench import (
    WorkbenchActionAffordanceList,
    WorkbenchEdge,
    WorkbenchEntityMemory,
    WorkbenchEntityProfile,
    WorkbenchGraph,
    WorkbenchLens,
    WorkbenchNode,
    workbench_read_boundary,
)

_HYPOTHESIS_ENTITY_PREFIXES = (
    "hypothesis-overview:",
    "hypothesis:",
    "hypothesis-evidence:",
    "structural-signal:",
    "hypothesis-event:",
    "hypothesis-score:",
    "hypothesis-proposed-action:",
)

_TERMINAL_HYPOTHESIS_STATUSES = {"dismissed", "duplicate", "promoted", "stale"}
_OPEN_HYPOTHESIS_STATUSES = {"new", "needs_verification", "reviewing"}


def build_hypothesis_lens_graph(
    *,
    program_id: UUID,
    hypotheses: list[Mapping[str, Any]],
    evidence_rows: list[Mapping[str, Any]],
    signal_rows: list[Mapping[str, Any]],
    event_rows: list[Mapping[str, Any]],
    score_rows: list[Mapping[str, Any]],
    proposal_rows: list[Mapping[str, Any]],
    seed: str | None,
    depth: int,
    limit: int,
) -> WorkbenchGraph:
    """Build a persisted hypothesis reasoning graph.

    The graph is intentionally advisory. Hypothesis nodes represent candidates
    and review state, not accepted findings or execution authority.
    """
    evidence_by_hypothesis = _group(evidence_rows, "hypothesis_id")
    events_by_hypothesis = _group(event_rows, "hypothesis_id")
    scores_by_hypothesis = _group(score_rows, "hypothesis_id")
    signals_by_fingerprint = {str(row["evidence_fingerprint"]): row for row in signal_rows}
    proposals_by_hypothesis = _proposals_by_hypothesis(proposal_rows, hypotheses)

    nodes: list[WorkbenchNode] = []
    edges: list[WorkbenchEdge] = []
    node_ids: set[str] = set()
    edge_ids: set[str] = set()

    def add_node(node: WorkbenchNode) -> None:
        if node.id not in node_ids:
            node_ids.add(node.id)
            nodes.append(node)

    def add_edge(edge: WorkbenchEdge) -> None:
        if edge.id not in edge_ids:
            edge_ids.add(edge.id)
            edges.append(edge)

    root = _overview_node(program_id, hypotheses, evidence_rows, signal_rows, event_rows, proposal_rows)
    add_node(root)

    for hypothesis in hypotheses:
        hypothesis_id = str(hypothesis["hypothesis_id"])
        hypothesis_node = _hypothesis_node(hypothesis, evidence_by_hypothesis.get(hypothesis_id, []))
        add_node(hypothesis_node)
        add_edge(_hypothesis_edge(root.id, hypothesis_node.id, "HAS_HYPOTHESIS", "has hypothesis", _status_delta(hypothesis.get("status"))))

        for fingerprint in _list(hypothesis.get("source_signal_fingerprints")):
            signal = signals_by_fingerprint.get(str(fingerprint))
            if signal is None:
                continue
            signal_node = _signal_node(signal)
            add_node(signal_node)
            add_edge(_hypothesis_edge(signal_node.id, hypothesis_node.id, "SUPPORTS_HYPOTHESIS", "supports hypothesis"))
            add_edge(_hypothesis_edge(root.id, signal_node.id, "HAS_SIGNAL", "has signal"))

        for evidence in evidence_by_hypothesis.get(hypothesis_id, []):
            evidence_node = _evidence_node(evidence)
            add_node(evidence_node)
            add_edge(_hypothesis_edge(evidence_node.id, hypothesis_node.id, "EVIDENCE_FOR", "evidence for"))

        for event in events_by_hypothesis.get(hypothesis_id, []):
            event_node = _event_node(event)
            add_node(event_node)
            add_edge(_hypothesis_edge(hypothesis_node.id, event_node.id, "HAS_CRITIC_EVENT", "has critic event", _event_delta(event.get("event_type"))))

        for score in scores_by_hypothesis.get(hypothesis_id, []):
            score_node = _score_node(score)
            add_node(score_node)
            add_edge(_hypothesis_edge(hypothesis_node.id, score_node.id, "HAS_SCORE_HISTORY", "has score history"))

        for proposal in proposals_by_hypothesis.get(hypothesis_id, []):
            proposal_node = _proposal_node(proposal)
            add_node(proposal_node)
            add_edge(_hypothesis_edge(hypothesis_node.id, proposal_node.id, "HAS_PROPOSED_ACTION", "has proposed action", _proposal_delta(proposal.get("status"))))

    nodes, edges = _select_graph(nodes, edges, seed=seed, limit=max(1, min(limit, 500)))
    return WorkbenchGraph(
        program_id=program_id,
        lens=WorkbenchLens.HYPOTHESIS,
        seed=seed,
        depth=depth,
        nodes=nodes,
        edges=edges,
        counts={
            "nodes": len(nodes),
            "edges": len(edges),
            "hypotheses": len(hypotheses),
            "signals": len(signal_rows),
            "evidence_refs": len(evidence_rows),
            "events": len(event_rows),
            "score_history": len(score_rows),
            "proposed_actions": len(proposal_rows),
        },
        boundary=workbench_read_boundary(surface="hypothesis_lens_reasoning_read_model"),
    )


def is_hypothesis_entity_key(entity_key: str) -> bool:
    return entity_key.startswith(_HYPOTHESIS_ENTITY_PREFIXES)


def hypothesis_entity_profile_from_graph(
    *,
    program_id: UUID,
    entity_key: str,
    graph: WorkbenchGraph,
) -> WorkbenchEntityProfile | None:
    node = _node_by_entity_key(graph, entity_key)
    if node is None:
        return None
    related_hypotheses = []
    related_actions = []
    if node.node_type != "research_hypothesis":
        related_hypotheses = _neighbor_summaries(graph, node.id, node_type="research_hypothesis")
    if node.node_type == "research_hypothesis":
        related_actions = _neighbor_summaries(graph, node.id, node_type="hypothesis_proposed_action")
    return WorkbenchEntityProfile(
        program_id=program_id,
        entity_key=node.entity_key,
        profile={
            "node_id": node.id,
            "node_type": node.node_type,
            "label": node.label,
            "caption": node.caption,
            "hypothesis_is_finding": False,
            "execution_surface": False,
        },
        properties=node.properties,
        evidence_refs=node.evidence_refs,
        related_hypotheses=related_hypotheses,
        related_actions=related_actions,
        memory_pointers=node.source_refs,
        boundary=workbench_read_boundary(surface="hypothesis_entity_profile"),
    )


def hypothesis_entity_memory_from_graph(
    *,
    program_id: UUID,
    entity_key: str,
    graph: WorkbenchGraph,
) -> WorkbenchEntityMemory | None:
    node = _node_by_entity_key(graph, entity_key)
    if node is None:
        return None
    adjacent_nodes = _adjacent_nodes(graph, node.id)
    fragments = [_node_fragment(node), *[_node_fragment(item) for item in adjacent_nodes[:25]]]
    evidence_refs = _dedupe_refs([*node.evidence_refs, *[ref for item in adjacent_nodes for ref in item.evidence_refs]])
    return WorkbenchEntityMemory(
        program_id=program_id,
        entity_key=node.entity_key,
        fragments=fragments,
        tree_nodes=[_tree_node(item, parent_id=node.id if item.id != node.id else None) for item in [node, *adjacent_nodes[:25]]],
        summaries=[
            {
                "kind": "hypothesis_read_model_summary",
                "entity_key": node.entity_key,
                "hypothesis_is_finding": False,
                "summary_is_truth": False,
                "execution_surface": False,
                "nodes_in_context": 1 + len(adjacent_nodes[:25]),
                "evidence_ref_count": len(evidence_refs),
                "not_semantics": "finding/proof/verdict/confirmed_vulnerability",
            }
        ],
        evidence_refs=evidence_refs,
        boundary=workbench_read_boundary(surface="hypothesis_entity_memory"),
    )


def hypothesis_entity_actions(*, program_id: UUID, entity_key: str) -> WorkbenchActionAffordanceList:
    return WorkbenchActionAffordanceList(
        program_id=program_id,
        entity_key=entity_key,
        actions=[],
        boundary=workbench_read_boundary(surface="hypothesis_lens_read_only_no_action_affordances"),
    )


def _overview_node(
    program_id: UUID,
    hypotheses: list[Mapping[str, Any]],
    evidence_rows: list[Mapping[str, Any]],
    signal_rows: list[Mapping[str, Any]],
    event_rows: list[Mapping[str, Any]],
    proposal_rows: list[Mapping[str, Any]],
) -> WorkbenchNode:
    open_count = sum(1 for row in hypotheses if str(row.get("status")) in _OPEN_HYPOTHESIS_STATUSES)
    terminal_count = sum(1 for row in hypotheses if str(row.get("status")) in _TERMINAL_HYPOTHESIS_STATUSES)
    return WorkbenchNode(
        id=f"hypothesis-overview:{program_id}",
        entity_key=f"hypothesis-overview:{program_id}",
        node_type="hypothesis_overview",
        label="Hypothesis overview",
        caption=f"{open_count} open · {terminal_count} terminal · {len(evidence_rows)} evidence refs",
        properties={
            "program_id": str(program_id),
            "hypothesis_is_finding": False,
            "execution_surface": False,
        },
        metadata={"hypothesis_contract": _hypothesis_contract()},
        badges=["hypothesis", "read-only"],
        metrics={
            "hypotheses": len(hypotheses),
            "open_hypotheses": open_count,
            "terminal_hypotheses": terminal_count,
            "signals": len(signal_rows),
            "evidence_refs": len(evidence_rows),
            "events": len(event_rows),
            "proposed_actions": len(proposal_rows),
        },
        confidence=1.0 if hypotheses else 0.0,
        source_refs=[{"type": "research_hypotheses", "id": str(program_id)}],
    )


def _hypothesis_node(row: Mapping[str, Any], evidence_rows: list[Mapping[str, Any]]) -> WorkbenchNode:
    hypothesis_id = str(row["hypothesis_id"])
    status = str(row.get("status") or "unknown")
    score = _int(row.get("priority_score"), 0)
    confidence = _float(row.get("confidence"), 0.0)
    return WorkbenchNode(
        id=f"hypothesis:{hypothesis_id}",
        entity_key=f"hypothesis:{hypothesis_id}",
        node_type="research_hypothesis",
        label=str(row.get("hypothesis_type") or "hypothesis"),
        caption=f"{status} · score {score} · {len(evidence_rows)} evidence refs",
        properties={
            "hypothesis_id": hypothesis_id,
            "hypothesis_type": row.get("hypothesis_type"),
            "hypothesis_fingerprint": row.get("hypothesis_fingerprint"),
            "status": status,
            "state_version": _int(row.get("state_version"), 1),
            "priority_score": score,
            "confidence": confidence,
            "safety_level": row.get("safety_level"),
            "score_version": row.get("score_version"),
            "inputs_hash": row.get("inputs_hash"),
            "duplicate_of_hypothesis_id": _str_or_none(row.get("duplicate_of_hypothesis_id")),
            "first_seen": _iso(row.get("first_seen")),
            "last_seen": _iso(row.get("last_seen")),
            "updated_at": _iso(row.get("updated_at")),
            "hypothesis_is_finding": False,
        },
        metadata={
            "source_signal_fingerprints": _list(row.get("source_signal_fingerprints")),
            "hypothesis_contract": _hypothesis_contract(),
        },
        badges=_hypothesis_badges(row),
        metrics={"priority_score": score, "confidence": confidence, "evidence_count": len(evidence_rows)},
        evidence_refs=[_hypothesis_ref(row), *[_evidence_ref(item) for item in evidence_rows]],
        action_affordance_count=0,
        staleness="stale" if status == "stale" else "fresh" if status in _OPEN_HYPOTHESIS_STATUSES else "unchanged",
        confidence=confidence,
        source_refs=[_hypothesis_ref(row)],
    )


def _signal_node(row: Mapping[str, Any]) -> WorkbenchNode:
    signal_id = str(row["signal_id"])
    signal_type = str(row.get("signal_type") or "signal")
    return WorkbenchNode(
        id=f"structural-signal:{signal_id}",
        entity_key=f"structural-signal:{signal_id}",
        node_type="structural_signal",
        label=signal_type,
        caption=f"{row.get('rule_id')} · confidence {_float(row.get('confidence'), 0.0):.2f}",
        properties={
            "signal_id": signal_id,
            "signal_type": signal_type,
            "signal_version": row.get("signal_version"),
            "rule_id": row.get("rule_id"),
            "rule_version": row.get("rule_version"),
            "asset_type": row.get("asset_type"),
            "asset_id": row.get("asset_id"),
            "observation_id": _str_or_none(row.get("observation_id")),
            "evidence_fingerprint": row.get("evidence_fingerprint"),
            "created_at": _iso(row.get("created_at")),
            "signal_is_verdict": False,
        },
        metadata={"payload": sanitize_json(_dict(row.get("payload_json"))), "hypothesis_contract": _hypothesis_contract()},
        badges=["signal", signal_type],
        metrics={"confidence": _float(row.get("confidence"), 0.0)},
        evidence_refs=[{"type": "research_signal", "id": signal_id}],
        staleness="unknown",
        confidence=_float(row.get("confidence"), 0.0),
        source_refs=[{"type": "research_signal", "id": signal_id}],
    )


def _evidence_node(row: Mapping[str, Any]) -> WorkbenchNode:
    evidence_id = str(row["evidence_id"])
    safe_excerpt = row.get("safe_excerpt") if row.get("safe_for_search") else None
    return WorkbenchNode(
        id=f"hypothesis-evidence:{evidence_id}",
        entity_key=f"hypothesis-evidence:{evidence_id}",
        node_type="hypothesis_evidence",
        label=str(row.get("claim_type") or "evidence"),
        caption=sanitize_text(str(row.get("claim") or ""), limit=180).safe_excerpt,
        properties={
            "evidence_id": evidence_id,
            "hypothesis_id": str(row["hypothesis_id"]),
            "ref_type": row.get("ref_type"),
            "ref_id": row.get("ref_id"),
            "field_path": row.get("field_path"),
            "role": row.get("role"),
            "claim_type": row.get("claim_type"),
            "evidence_fingerprint": row.get("evidence_fingerprint"),
            "evidence_source": row.get("evidence_source"),
            "safe_excerpt": sanitize_text(str(safe_excerpt), limit=500).safe_excerpt if safe_excerpt else None,
            "safe_excerpt_truncated": bool(row.get("safe_excerpt_truncated")),
            "safe_for_search": bool(row.get("safe_for_search")),
            "safe_for_llm": bool(row.get("safe_for_llm")),
            "created_at": _iso(row.get("created_at")),
        },
        metadata={
            "sanitizer_version": row.get("sanitizer_version"),
            "redaction_policy_version": row.get("redaction_policy_version"),
            "sensitivity_level": row.get("sensitivity_level"),
            "redaction_rules_triggered": _list(row.get("redaction_rules_triggered")),
            "raw_body_exposed": False,
        },
        badges=["evidence", str(row.get("role") or "context")],
        evidence_refs=[_evidence_ref(row)],
        staleness="unknown",
        confidence=1.0 if row.get("safe_for_search") else 0.5,
        source_refs=[_evidence_ref(row)],
    )


def _event_node(row: Mapping[str, Any]) -> WorkbenchNode:
    event_id = str(row["event_id"])
    event_type = str(row.get("event_type") or "event")
    return WorkbenchNode(
        id=f"hypothesis-event:{event_id}",
        entity_key=f"hypothesis-event:{event_id}",
        node_type="hypothesis_critic_status",
        label=event_type.replace("_", " "),
        caption=f"v{row.get('aggregate_version')} · {row.get('actor')}",
        properties={
            "event_id": event_id,
            "hypothesis_id": str(row["hypothesis_id"]),
            "event_type": event_type,
            "aggregate_version": _int(row.get("aggregate_version"), 1),
            "actor": row.get("actor"),
            "reason": sanitize_text(str(row.get("reason") or ""), limit=500).safe_excerpt if row.get("reason") else None,
            "created_at": _iso(row.get("created_at")),
        },
        metadata={"payload": sanitize_json(_dict(row.get("payload_json"))), "critic_status_is_finding": False},
        badges=["critic", event_type],
        evidence_refs=[{"type": "research_hypothesis_event", "id": event_id}],
        staleness="fresh",
        confidence=0.8,
        source_refs=[{"type": "research_hypothesis_event", "id": event_id}],
    )


def _score_node(row: Mapping[str, Any]) -> WorkbenchNode:
    score_id = str(row["score_id"])
    return WorkbenchNode(
        id=f"hypothesis-score:{score_id}",
        entity_key=f"hypothesis-score:{score_id}",
        node_type="hypothesis_score_history",
        label=str(row.get("score_version") or "score"),
        caption=f"score {_int(row.get('priority_score'), 0)} · confidence {_float(row.get('confidence'), 0.0):.2f}",
        properties={
            "score_id": score_id,
            "hypothesis_id": str(row["hypothesis_id"]),
            "score_version": row.get("score_version"),
            "priority_score": _int(row.get("priority_score"), 0),
            "confidence": _float(row.get("confidence"), 0.0),
            "safety_level": row.get("safety_level"),
            "inputs_hash": row.get("inputs_hash"),
            "created_at": _iso(row.get("created_at")),
            "score_is_verdict": False,
        },
        metadata={"factors": sanitize_json(_dict(row.get("factors_json"))), "hypothesis_contract": _hypothesis_contract()},
        badges=["score", str(row.get("score_version") or "version")],
        metrics={"priority_score": _int(row.get("priority_score"), 0), "confidence": _float(row.get("confidence"), 0.0)},
        evidence_refs=[{"type": "research_hypothesis_score_history", "id": score_id}],
        confidence=_float(row.get("confidence"), 0.0),
        source_refs=[{"type": "research_hypothesis_score_history", "id": score_id}],
    )


def _proposal_node(row: Mapping[str, Any]) -> WorkbenchNode:
    proposal_id = str(row["proposal_id"])
    status = str(row.get("status") or "pending")
    return WorkbenchNode(
        id=f"hypothesis-proposed-action:{proposal_id}",
        entity_key=f"hypothesis-proposed-action:{proposal_id}",
        node_type="hypothesis_proposed_action",
        label=str(row.get("title") or row.get("capability_id") or "proposed action"),
        caption=sanitize_text(str(row.get("summary") or ""), limit=160).safe_excerpt or status,
        properties={
            "proposal_id": proposal_id,
            "proposal_type": row.get("proposal_type"),
            "status": status,
            "agent_key": row.get("agent_key"),
            "capability_id": row.get("capability_id"),
            "profile_id": row.get("profile_id"),
            "priority": row.get("priority"),
            "expected_gain": sanitize_text(str(row.get("expected_gain") or ""), limit=400).safe_excerpt,
            "accepted_action_id": _str_or_none(row.get("accepted_action_id")),
            "created_at": _iso(row.get("created_at")),
            "updated_at": _iso(row.get("updated_at")),
            "proposal_is_execution": False,
        },
        metadata={
            "context_refs": sanitize_json(_list(row.get("context_refs"))),
            "action_params": sanitize_json(_dict(row.get("action_params"))),
            "metadata": sanitize_json(_dict(row.get("metadata"))),
            "review_feedback": sanitize_json(_dict(row.get("review_feedback"))),
            "not_execution_surface": True,
        },
        badges=["proposed action", status],
        evidence_refs=[{"type": "agent_action_proposal", "id": proposal_id}],
        staleness="fresh" if status == "pending" else "unchanged",
        confidence=0.6,
        source_refs=[{"type": "agent_action_proposal", "id": proposal_id}],
    )


def _hypothesis_edge(
    source: str,
    target: str,
    relationship_type: str,
    label: str,
    delta_state: str = "unchanged",
) -> WorkbenchEdge:
    return WorkbenchEdge(
        id=f"edge:{source}:{relationship_type}:{target}",
        source=source,
        target=target,
        relationship_type=relationship_type,
        label=label,
        confidence=1.0,
        delta_state=delta_state,
        source_projection="hypothesis_read_model",
    )


def _hypothesis_contract() -> dict[str, Any]:
    return {
        "hypothesis_is_finding": False,
        "finding_promotion": False,
        "execution_surface": False,
        "proposal_creation": False,
        "not_semantics": "finding/proof/verdict/confirmed_vulnerability",
    }


def _hypothesis_badges(row: Mapping[str, Any]) -> list[str]:
    badges = ["hypothesis", str(row.get("status") or "unknown")]
    safety = row.get("safety_level")
    if safety:
        badges.append(str(safety))
    return badges


def _status_delta(status: object) -> str:
    text = str(status or "").lower()
    if text in {"new", "needs_verification", "reviewing"}:
        return "added"
    if text in {"dismissed", "duplicate", "stale"}:
        return "removed"
    if text == "promoted":
        return "changed"
    return "unchanged"


def _event_delta(event_type: object) -> str:
    text = str(event_type or "").lower()
    if "created" in text or "new" in text:
        return "added"
    if "dismiss" in text or "stale" in text or "duplicate" in text:
        return "removed"
    return "changed"


def _proposal_delta(status: object) -> str:
    text = str(status or "").lower()
    if text == "pending":
        return "added"
    if text in {"rejected", "suppressed", "expired"}:
        return "removed"
    if text == "accepted":
        return "changed"
    return "unchanged"


def _select_graph(
    nodes: list[WorkbenchNode],
    edges: list[WorkbenchEdge],
    *,
    seed: str | None,
    limit: int,
) -> tuple[list[WorkbenchNode], list[WorkbenchEdge]]:
    if not seed:
        selected_nodes = nodes[:limit]
        selected_ids = {node.id for node in selected_nodes}
        return selected_nodes, [edge for edge in edges if edge.source in selected_ids and edge.target in selected_ids]
    seed_ids = {node.id for node in nodes if seed in {node.id, node.entity_key}}
    if not seed_ids:
        return [], []
    selected_ids = set(seed_ids)
    for edge in edges:
        if edge.source in seed_ids:
            selected_ids.add(edge.target)
        if edge.target in seed_ids:
            selected_ids.add(edge.source)
    selected_nodes = [node for node in nodes if node.id in selected_ids][:limit]
    selected_ids = {node.id for node in selected_nodes}
    return selected_nodes, [edge for edge in edges if edge.source in selected_ids and edge.target in selected_ids]


def _proposals_by_hypothesis(
    proposal_rows: list[Mapping[str, Any]],
    hypotheses: list[Mapping[str, Any]],
) -> dict[str, list[Mapping[str, Any]]]:
    hypothesis_ids = {str(row["hypothesis_id"]) for row in hypotheses}
    fingerprints = {str(row.get("hypothesis_fingerprint")): str(row["hypothesis_id"]) for row in hypotheses if row.get("hypothesis_fingerprint")}
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for proposal in proposal_rows:
        text = str(sanitize_json({
            "context_refs": _list(proposal.get("context_refs")),
            "metadata": _dict(proposal.get("metadata")),
            "action_params": _dict(proposal.get("action_params")),
        }))
        matched = {hypothesis_id for hypothesis_id in hypothesis_ids if hypothesis_id in text}
        matched.update(hypothesis_id for fingerprint, hypothesis_id in fingerprints.items() if fingerprint and fingerprint in text)
        for hypothesis_id in matched:
            grouped[hypothesis_id].append(proposal)
    return grouped


def _neighbor_summaries(graph: WorkbenchGraph, node_id: str, *, node_type: str) -> list[dict[str, Any]]:
    adjacent_ids = {edge.source for edge in graph.edges if edge.target == node_id} | {edge.target for edge in graph.edges if edge.source == node_id}
    nodes_by_id = {node.id: node for node in graph.nodes}
    return [
        {"entity_key": node.entity_key, "node_type": node.node_type, "label": node.label, "caption": node.caption}
        for item_id in adjacent_ids
        if (node := nodes_by_id.get(item_id)) is not None and node.node_type == node_type
    ]


def _adjacent_nodes(graph: WorkbenchGraph, node_id: str) -> list[WorkbenchNode]:
    adjacent_ids = {edge.source for edge in graph.edges if edge.target == node_id} | {edge.target for edge in graph.edges if edge.source == node_id}
    nodes_by_id = {node.id: node for node in graph.nodes}
    return [node for item_id in adjacent_ids if (node := nodes_by_id.get(item_id)) is not None]


def _node_by_entity_key(graph: WorkbenchGraph, entity_key: str) -> WorkbenchNode | None:
    return next((node for node in graph.nodes if node.entity_key == entity_key or node.id == entity_key), None)


def _node_fragment(node: WorkbenchNode) -> dict[str, Any]:
    return {
        "kind": node.node_type,
        "id": node.id,
        "entity_key": node.entity_key,
        "label": node.label,
        "caption": node.caption,
        "properties": node.properties,
        "metrics": node.metrics,
        "evidence_refs": node.evidence_refs,
        "hypothesis_is_finding": False,
        "execution_surface": False,
    }


def _tree_node(node: WorkbenchNode, *, parent_id: str | None) -> dict[str, Any]:
    return {
        "id": node.id,
        "parent_id": parent_id,
        "kind": node.node_type,
        "label": node.label,
        "evidence_refs": node.evidence_refs,
    }


def _hypothesis_ref(row: Mapping[str, Any]) -> dict[str, Any]:
    return {"type": "research_hypothesis", "id": str(row["hypothesis_id"])}


def _evidence_ref(row: Mapping[str, Any]) -> dict[str, Any]:
    return {"type": str(row.get("ref_type") or "research_hypothesis_evidence"), "id": str(row.get("ref_id") or row["evidence_id"])}


def _dedupe_refs(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, Any]] = []
    for ref in refs:
        key = (str(ref.get("type") or ""), str(ref.get("id") or ref.get("payload") or ""))
        if key in seen:
            continue
        seen.add(key)
        result.append(ref)
    return result


def _group(rows: list[Mapping[str, Any]], key: str) -> dict[str, list[Mapping[str, Any]]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row[key])].append(row)
    return grouped


def _dict(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list(value: object) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _int(value: object, default: int = 0) -> int:
    try:
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _float(value: object, default: float = 0.0) -> float:
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _str_or_none(value: object) -> str | None:
    return str(value) if value is not None else None


def _iso(value: object) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else None
