from __future__ import annotations

import json
from typing import Any


def print_json(data: dict[str, Any]) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))


def title(value: str) -> str:
    return f"== {value} =="


def section(value: str) -> str:
    return f"-- {value} --"


def one_line(value: Any, *, limit: int = 180) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def bool_mark(value: Any) -> str:
    return "ok" if bool(value) else "stale"


def queue_summary(queue: dict[str, Any]) -> str:
    applied = int(queue.get("applied") or 0)
    applied_suffix = f" applied={applied}" if applied else ""
    return (
        f"pending={queue.get('pending', 0)} "
        f"locked={queue.get('locked', 0)} "
        f"failed={queue.get('failed', 0)} "
        f"dead={queue.get('dead', 0)} "
        f"processed={queue.get('processed', 0)}"
        f"{applied_suffix}"
    )


def render_usage(usage: dict[str, Any]) -> list[str]:
    if not usage:
        return []
    lines: list[str] = []
    selected = usage.get("selected_modes") or {}
    if selected:
        parts = [f"{mode}={selected.get(mode, 0)}" for mode in ("none", "cheap", "normal", "deep")]
        lines.append("Agent runtime: " + " · ".join(parts))
    warnings = usage.get("warnings") or []
    if warnings:
        lines.append("Runtime warnings: " + ", ".join(str(item) for item in warnings[:4]))
    return lines


def append_boundary(lines: list[str], boundary: dict[str, Any]) -> None:
    if not boundary:
        return
    lines.append("")
    lines.append(section("Boundary"))
    for key in sorted(boundary):
        value = boundary[key]
        if isinstance(value, list):
            value = ", ".join(str(item) for item in value)
        lines.append(f"  {key}: {value}")


def proposal_line(proposal: dict[str, Any]) -> str:
    return (
        f"  {proposal.get('proposal_id')}  [{proposal.get('status')}] "
        f"{proposal.get('priority')}/{proposal.get('risk_level')}  "
        f"{proposal.get('agent_key')}: {proposal.get('title')}"
    )


def experience_proposal_line(proposal: dict[str, Any]) -> str:
    return (
        f"  {proposal.get('proposal_id')}  [{proposal.get('status')}] "
        f"rank={proposal.get('rank')} score={proposal.get('utility_score')} "
        f"{proposal.get('capability_id')}/{proposal.get('profile_id')} "
        f"samples={proposal.get('sample_count')} sim={proposal.get('avg_similarity')}"
    )
