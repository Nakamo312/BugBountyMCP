from __future__ import annotations

from typing import Any

from .common import one_line, proposal_line, render_usage, section, title


def render_tasks(data: dict[str, Any]) -> str:
    lines = [title("Agent tasks")]
    items = data.get("items") or []
    if not items:
        lines.append("No agent tasks.")
        return "\n".join(lines)
    for task in items:
        lines.append(
            f"{task.get('task_id')}  [{task.get('status')}] "
            f"{task.get('target_agent')}: {task.get('title')}"
        )
        excerpt = one_line(task.get("prompt_excerpt"))
        if excerpt:
            lines.append(f"  {excerpt}")
    return "\n".join(lines)


def render_task_detail(snapshot: dict[str, Any]) -> str:
    task = snapshot.get("task") or {}
    lines = [title(f"Agent task: {task.get('title') or task.get('task_id')}")]
    lines.append(f"Task: {task.get('task_id')}  Status: {task.get('status')}  Agent: {task.get('target_agent')}")
    counts = snapshot.get("counts") or {}
    if counts:
        lines.append(
            "Counts: "
            f"messages={counts.get('messages', 0)} · "
            f"proposals={counts.get('proposals', 0)} · "
            f"accepted_actions={counts.get('accepted_actions', 0)} · "
            f"outcomes={counts.get('related_outcomes', 0)}"
        )
    compact = snapshot.get("compact_context") or {}
    lines.extend(render_usage(compact.get("agent_runtime_usage") or {}))
    lines.append("")
    lines.append(section("Thread"))
    for message in snapshot.get("messages") or []:
        prefix = f"{message.get('role')}"
        if message.get("agent_key"):
            prefix += f"/{message.get('agent_key')}"
        prefix += f"/{message.get('message_kind')}"
        lines.append(f"{prefix}: {one_line(message.get('body'), limit=500)}")
    lines.append("")
    lines.append(section("Proposals"))
    proposals = snapshot.get("proposals") or []
    if not proposals:
        lines.append("  No proposals for this task.")
    for proposal in proposals:
        lines.append(proposal_line(proposal))
        summary = one_line(proposal.get("summary"), limit=280)
        if summary:
            lines.append(f"    {summary}")
    accepted = snapshot.get("accepted_actions") or []
    if accepted:
        lines.append("")
        lines.append(section("Accepted actions"))
        for action in accepted:
            lines.append(f"  {action.get('action_id')}  [{action.get('status')}] {action.get('title') or ''}")
    outcomes = snapshot.get("related_outcomes") or []
    if outcomes:
        lines.append("")
        lines.append(section("Related outcomes"))
        for outcome in outcomes[:10]:
            lines.append(
                f"  {outcome.get('outcome_id')}  "
                f"{outcome.get('capability_id')}/{outcome.get('profile_id')}  "
                f"gain={outcome.get('information_gain_score')}  status={outcome.get('status')}"
            )
    return "\n".join(lines)


def render_agent_task_created(data: dict[str, Any]) -> str:
    task = data.get("task") or {}
    message = data.get("first_message") or {}
    lines = [title("Agent task created")]
    lines.append(f"Task: {task.get('task_id')}")
    lines.append(f"Agent: {task.get('target_agent')}  Status: {task.get('status')}")
    lines.append(f"Prompt: {one_line(message.get('body') or task.get('prompt_excerpt'), limit=400)}")
    lines.append("")
    lines.append(f"Next: bb task show {task.get('task_id')}")
    return "\n".join(lines)


def render_message_created(data: dict[str, Any]) -> str:
    return "\n".join(
        [
            title("Follow-up queued"),
            f"Message: {data.get('message_id')}",
            f"Task: {data.get('task_id')}",
            f"Body: {one_line(data.get('body'), limit=400)}",
        ]
    )
