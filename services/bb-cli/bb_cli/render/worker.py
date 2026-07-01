from __future__ import annotations

from typing import Any

from .common import one_line, proposal_line, section, title


def render_worker_once(payload: dict[str, Any]) -> str:
    worker = payload.get("worker") or payload
    lines = [title("Agent worker run-once")]
    lines.extend(render_worker(worker))
    return "\n".join(lines)


def render_task_run_agent(payload: dict[str, Any]) -> str:
    created = payload.get("created") or {}
    detail = payload.get("task_detail") or {}
    task = (created.get("task") or {}) or (detail.get("task") or {})
    messages = detail.get("messages") or []
    proposals = detail.get("proposals") or []
    lines = [title("Agent task run")]
    if task:
        lines.append(f"Task: {task.get('task_id')}  Agent: {task.get('target_agent')}  Status: {task.get('status')}")
    else:
        lines.append("Task: -")
    prompt = one_line((created.get("first_message") or {}).get("body") or task.get("prompt_excerpt"), limit=300)
    if prompt:
        lines.append(f"Prompt: {prompt}")
    lines.append("")
    lines.append(section("Worker"))
    lines.extend(render_worker(payload.get("worker") or {}))
    lines.append("")
    lines.append(section("Latest thread"))
    if not messages:
        lines.append("  No thread messages yet.")
    for message in messages[-6:]:
        prefix = f"{message.get('role')}"
        if message.get("agent_key"):
            prefix += f"/{message.get('agent_key')}"
        prefix += f"/{message.get('message_kind')}"
        lines.append(f"  {prefix}: {one_line(message.get('body'), limit=360)}")
    lines.append("")
    lines.append(section("Proposals"))
    if not proposals:
        lines.append("  No proposals yet. If the worker processed 0 messages, run: bb task run-agent")
    for proposal in proposals[:10]:
        lines.append(proposal_line(proposal))
        summary = one_line(proposal.get("summary"), limit=240)
        if summary:
            lines.append(f"    {summary}")
        if proposal.get("status") == "pending":
            lines.append(f"    Next: bb proposal accept {proposal.get('proposal_id')} --target <target>")
            lines.append(f"          bb proposal reject {proposal.get('proposal_id')} --reason <reason>")
            lines.append(f"          bb proposal suppress {proposal.get('proposal_id')} --reason <reason>")
    task_id = task.get("task_id") or (detail.get("task") or {}).get("task_id")
    if task_id:
        lines.append("")
        lines.append(f"Open detail: bb task show {task_id}")
    return "\n".join(lines)


def render_dev_cycle(payload: dict[str, Any]) -> str:
    return render_task_run_agent(payload)


def render_worker(worker: dict[str, Any]) -> list[str]:
    if not worker:
        return ["  Worker result is missing."]
    status = worker.get("status")
    command = " ".join(str(part) for part in (worker.get("command") or [])) or "-"
    lines = [f"  Status: {status}  Exit: {worker.get('exit_code')}  Command: {command}"]
    stdout = one_line(worker.get("stdout"), limit=500)
    stderr = one_line(worker.get("stderr"), limit=500)
    if stdout:
        lines.append(f"  stdout: {stdout}")
    if stderr:
        lines.append(f"  stderr: {stderr}")
    if worker.get("skipped"):
        lines.append("  skipped: task was created; worker was not invoked")
    return lines
