from __future__ import annotations

from typing import Any

from .common import one_line, proposal_line, render_usage, section, title


def render_workspace(snapshot: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(title("Campaign workspace"))
    lines.append(f"Program: {snapshot.get('program_id')}  Campaign: {snapshot.get('campaign_id') or '-'}")
    counts = snapshot.get("counts") or {}
    if counts:
        lines.append(
            "Counts: "
            f"tasks={counts.get('tasks', 0)} · "
            f"pending_agent_proposals={counts.get('pending_agent_proposals', 0)} · "
            f"actions={counts.get('action_queue', 0)} · "
            f"decisions={counts.get('recent_decisions', 0)}"
        )
    usage = snapshot.get("agent_runtime_usage") or {}
    lines.extend(render_usage(usage))
    lines.append("")
    lines.append(section("Tasks"))
    tasks = snapshot.get("tasks") or []
    if not tasks:
        lines.append("  No agent tasks yet. Use: bb task create \"...\"")
    for task_card in tasks[:20]:
        task = task_card.get("task") or task_card
        lines.append(
            f"  {task.get('task_id')}  [{task.get('status')}] "
            f"{task.get('target_agent')}: {task.get('title')}"
        )
        for message in (task_card.get("messages") or [])[-2:]:
            lines.append(f"    {message.get('role')}/{message.get('message_kind')}: {one_line(message.get('body'))}")
    lines.append("")
    lines.append(section("Pending proposals"))
    proposals = snapshot.get("pending_agent_proposals") or []
    if not proposals:
        lines.append("  No pending agent proposals.")
    for proposal in proposals[:20]:
        lines.append(proposal_line(proposal))
    lines.append("")
    lines.append(section("Action queue"))
    actions = snapshot.get("action_queue") or []
    if not actions:
        lines.append("  No visible action requests.")
    for action in actions[:20]:
        item_title = action.get("title") or action.get("capability_id") or action.get("action_id")
        lines.append(f"  {action.get('action_id')}  [{action.get('status')}] {item_title}")
    return "\n".join(lines)
