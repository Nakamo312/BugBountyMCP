from __future__ import annotations

import json
from typing import Any, Iterable


def print_json(data: dict[str, Any]) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))


def render_workspace(snapshot: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(_title("Campaign workspace"))
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
    lines.extend(_render_usage(usage))
    lines.append("")
    lines.append(_section("Tasks"))
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
            lines.append(f"    {message.get('role')}/{message.get('message_kind')}: {_one_line(message.get('body'))}")
    lines.append("")
    lines.append(_section("Pending proposals"))
    proposals = snapshot.get("pending_agent_proposals") or []
    if not proposals:
        lines.append("  No pending agent proposals.")
    for proposal in proposals[:20]:
        lines.append(_proposal_line(proposal))
    lines.append("")
    lines.append(_section("Action queue"))
    actions = snapshot.get("action_queue") or []
    if not actions:
        lines.append("  No visible action requests.")
    for action in actions[:20]:
        title = action.get("title") or action.get("capability_id") or action.get("action_id")
        lines.append(f"  {action.get('action_id')}  [{action.get('status')}] {title}")
    return "\n".join(lines)


def render_tasks(data: dict[str, Any]) -> str:
    lines = [_title("Agent tasks")]
    items = data.get("items") or []
    if not items:
        lines.append("No agent tasks.")
        return "\n".join(lines)
    for task in items:
        lines.append(
            f"{task.get('task_id')}  [{task.get('status')}] "
            f"{task.get('target_agent')}: {task.get('title')}"
        )
        excerpt = _one_line(task.get("prompt_excerpt"))
        if excerpt:
            lines.append(f"  {excerpt}")
    return "\n".join(lines)


def render_task_detail(snapshot: dict[str, Any]) -> str:
    task = snapshot.get("task") or {}
    lines = [_title(f"Agent task: {task.get('title') or task.get('task_id')}")]
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
    lines.extend(_render_usage(compact.get("agent_runtime_usage") or {}))
    lines.append("")
    lines.append(_section("Thread"))
    for message in snapshot.get("messages") or []:
        prefix = f"{message.get('role')}"
        if message.get("agent_key"):
            prefix += f"/{message.get('agent_key')}"
        prefix += f"/{message.get('message_kind')}"
        lines.append(f"{prefix}: {_one_line(message.get('body'), limit=500)}")
    lines.append("")
    lines.append(_section("Proposals"))
    proposals = snapshot.get("proposals") or []
    if not proposals:
        lines.append("  No proposals for this task.")
    for proposal in proposals:
        lines.append(_proposal_line(proposal))
        summary = _one_line(proposal.get("summary"), limit=280)
        if summary:
            lines.append(f"    {summary}")
    accepted = snapshot.get("accepted_actions") or []
    if accepted:
        lines.append("")
        lines.append(_section("Accepted actions"))
        for action in accepted:
            lines.append(f"  {action.get('action_id')}  [{action.get('status')}] {action.get('title') or ''}")
    outcomes = snapshot.get("related_outcomes") or []
    if outcomes:
        lines.append("")
        lines.append(_section("Related outcomes"))
        for outcome in outcomes[:10]:
            lines.append(
                f"  {outcome.get('outcome_id')}  "
                f"{outcome.get('capability_id')}/{outcome.get('profile_id')}  "
                f"gain={outcome.get('information_gain_score')}  status={outcome.get('status')}"
            )
    return "\n".join(lines)


def render_agent_task_created(data: dict[str, Any]) -> str:
    task = (data.get("task") or {})
    message = (data.get("first_message") or {})
    lines = [_title("Agent task created")]
    lines.append(f"Task: {task.get('task_id')}")
    lines.append(f"Agent: {task.get('target_agent')}  Status: {task.get('status')}")
    lines.append(f"Prompt: {_one_line(message.get('body') or task.get('prompt_excerpt'), limit=400)}")
    lines.append("")
    lines.append(f"Next: bb task show {task.get('task_id')}")
    return "\n".join(lines)


def render_message_created(data: dict[str, Any]) -> str:
    return "\n".join(
        [
            _title("Follow-up queued"),
            f"Message: {data.get('message_id')}",
            f"Task: {data.get('task_id')}",
            f"Body: {_one_line(data.get('body'), limit=400)}",
        ]
    )


def render_proposals_from_workspace(snapshot: dict[str, Any]) -> str:
    lines = [_title("Pending proposals")]
    agent_proposals = snapshot.get("pending_agent_proposals") or []
    experience_proposals = snapshot.get("pending_experience_proposals") or []
    if not agent_proposals and not experience_proposals:
        lines.append("No pending proposals.")
        return "\n".join(lines)

    if agent_proposals:
        lines.append(_section("Agent action proposals"))
        for proposal in agent_proposals:
            lines.append(_proposal_line(proposal))
            summary = _one_line(proposal.get("summary"), limit=260)
            if summary:
                lines.append(f"  {summary}")
            lines.append(f"  Next: bb proposal accept {proposal.get('proposal_id')} --target <target>")

    if experience_proposals:
        if agent_proposals:
            lines.append("")
        lines.append(_section("Action experience proposals"))
        for proposal in experience_proposals:
            lines.append(_experience_proposal_line(proposal))
            explanation = proposal.get("explanation") or {}
            source = _one_line(explanation.get("source"), limit=180)
            if source:
                lines.append(f"  Source: {source}")
            lines.append(
                f"  Next: bb proposal accept {proposal.get('proposal_id')} --kind experience --target <target>"
            )
            lines.append(f"        bb proposal reject {proposal.get('proposal_id')} --kind experience --reason <reason>")
            lines.append(f"        bb proposal suppress {proposal.get('proposal_id')} --kind experience --reason <reason>")
    return "\n".join(lines)


def render_proposal_result(data: dict[str, Any], *, action: str) -> str:
    result = data.get("results") or data
    proposal = result.get("proposal") or {}
    lines = [_title(f"Proposal {action}")]
    lines.append(f"Proposal: {proposal.get('proposal_id')}  Status: {proposal.get('status')}")
    if action == "accepted":
        submission = result.get("action_submission") or {}
        lines.append(f"Action status: {submission.get('status')}")
        if submission.get("action"):
            lines.append(f"Action: {submission.get('action', {}).get('action_id')}")
    else:
        lines.append("Feedback was stored as learning signal.")
    return "\n".join(lines)


def render_activity(snapshot: dict[str, Any]) -> str:
    lines = [_title("Agent activity")]
    events = snapshot.get("events") or snapshot.get("items") or []
    if not events:
        lines.append("No activity events.")
        return "\n".join(lines)
    for event in events:
        lines.append(
            f"{event.get('created_at') or event.get('timestamp') or '-'}  "
            f"{event.get('event_type') or event.get('type')}: "
            f"{_one_line(event.get('title') or event.get('body') or event.get('summary'), limit=220)}"
        )
    next_after = snapshot.get("next_after")
    if next_after:
        lines.append("")
        lines.append(f"Next cursor: {next_after}")
    return "\n".join(lines)


def render_program_projection_overview(data: dict[str, Any], *, show_boundary: bool = False) -> str:
    lines = [_title("Program projection overview")]
    lines.append(f"Program: {data.get('program_id')}")
    lines.append(
        "Freshness: "
        f"surface_analysis={_bool_mark(data.get('surface_analysis_fresh'))} · "
        f"search_index={_bool_mark(data.get('search_index_fresh'))} · "
        f"ui_data={_bool_mark(data.get('ui_data_fresh'))}"
    )

    snapshot = data.get("latest_surface_snapshot") or {}
    analysis = data.get("latest_surface_analysis") or {}
    lines.append("")
    lines.append(_section("Surface state"))
    if snapshot:
        lines.append(
            "  Latest snapshot: "
            f"{snapshot.get('snapshot_id')}  "
            f"nodes={snapshot.get('node_count', 0)} "
            f"edges={snapshot.get('edge_count', 0)} "
            f"deltas={snapshot.get('delta_count', 0)}"
        )
    else:
        lines.append("  Latest snapshot: -")
    if analysis:
        lines.append(
            "  Latest analysis: "
            f"{analysis.get('analysis_run_id')}  "
            f"snapshot={analysis.get('snapshot_id')} "
            f"items={analysis.get('item_count', 0)}"
        )
    else:
        lines.append("  Latest analysis: -")

    lines.append("")
    lines.append(_section("Durable queues"))
    queue_names = [
        ("Graph projection events", "graph_projection_events"),
        ("Graph fact batches", "graph_fact_batches"),
        ("Surface analysis events", "surface_analysis_events"),
        ("Search projection events", "search_projection_events"),
    ]
    for label, key in queue_names:
        lines.append(f"  {label}: {_queue_summary(data.get(key) or {})}")

    search = data.get("search_index") or {}
    lines.append("")
    lines.append(_section("Search index"))
    lines.append(
        "  Components indexed: "
        f"{_bool_mark(search.get('surface_components_indexed'))}  "
        f"status={search.get('latest_surface_components_event_status') or '-'}"
    )
    lines.append(
        "  Deltas indexed: "
        f"{_bool_mark(search.get('surface_deltas_indexed'))}  "
        f"status={search.get('latest_surface_deltas_event_status') or '-'}"
    )

    proposals = data.get("experience_proposals") or {}
    lines.append("")
    lines.append(_section("Action experience proposals"))
    lines.append(
        "  "
        f"pending={proposals.get('pending', 0)} · "
        f"accepted={proposals.get('accepted', 0)} · "
        f"rejected={proposals.get('rejected', 0)} · "
        f"suppressed={proposals.get('suppressed', 0)}"
    )

    commands = data.get("suggested_commands") or []
    if commands:
        lines.append("")
        lines.append(_section("Suggested commands"))
        for command in commands[:10]:
            lines.append(f"  {command}")

    if show_boundary:
        boundary = data.get("boundary") or {}
        if boundary:
            lines.append("")
            lines.append(_section("Boundary"))
            for key in sorted(boundary):
                value = boundary[key]
                if isinstance(value, list):
                    value = ", ".join(str(item) for item in value)
                lines.append(f"  {key}: {value}")

    return "\n".join(lines)



def render_program_projection_plan(data: dict[str, Any], *, show_boundary: bool = False) -> str:
    lines = [_title("Program projection operator plan")]
    lines.append(f"Program: {data.get('program_id')}")
    lines.append(f"UI data fresh: {_bool_mark(data.get('ui_data_fresh'))}")
    lines.append(f"Steps: {data.get('step_count', 0)}")

    steps = data.get("steps") or []
    if not steps:
        lines.append("No operator steps returned.")
    else:
        lines.append("")
        lines.append(_section("Ordered steps"))
        for step in steps:
            lines.append(
                "  "
                f"{step.get('priority')}. [{step.get('severity')}] "
                f"{step.get('area')}: {step.get('title')}"
            )
            reason = _one_line(step.get("reason"), limit=260)
            if reason:
                lines.append(f"     Reason: {reason}")
            commands = step.get("commands") or []
            for command in commands:
                lines.append(f"     $ {command}")

    if show_boundary:
        boundary = data.get("boundary") or {}
        if boundary:
            lines.append("")
            lines.append(_section("Boundary"))
            for key in sorted(boundary):
                value = boundary[key]
                if isinstance(value, list):
                    value = ", ".join(str(item) for item in value)
                lines.append(f"  {key}: {value}")
    return "\n".join(lines)




def render_program_projection_audit(data: dict[str, Any], *, show_boundary: bool = False) -> str:
    lines = [_title("Program projection run-step audit")]
    lines.append(f"Path: {data.get('path')}")
    lines.append(f"Program: {data.get('program_id') or '-'}  Step: {data.get('step_id') or '*'}")
    lines.append(
        "Counts: "
        f"total_lines={data.get('total_lines', 0)} · "
        f"matched={data.get('matched_lines', 0)} · "
        f"skipped={data.get('skipped_lines', 0)}"
    )
    if not data.get("exists"):
        lines.append("Audit log does not exist yet.")
    events = data.get("events") or []
    if not events:
        lines.append("No matching audit events.")
    else:
        lines.append("")
        lines.append(_section("Events"))
        for event in events:
            mode = "execute" if event.get("execute") else "preview"
            statuses = event.get("statuses") or {}
            status_text = ", ".join(f"{key}={value}" for key, value in sorted(statuses.items())) or "none"
            lines.append(
                f"  {event.get('created_at') or '-'}  {event.get('audit_id') or '-'}  "
                f"[{mode}] {event.get('step_id') or '-'}  commands={event.get('command_count', 0)}  {status_text}"
            )
            title = _one_line(event.get("step_title"), limit=180)
            if title:
                lines.append(f"    {title}")
            for command in (event.get("commands") or [])[:3]:
                lines.append(f"    $ {command}")
            commands = event.get("commands") or []
            if len(commands) > 3:
                lines.append(f"    ... {len(commands) - 3} more command(s)")
    skipped = data.get("skipped") or []
    if skipped:
        lines.append("")
        lines.append(_section("Skipped malformed lines"))
        for item in skipped:
            lines.append(f"  line {item.get('line_number')}: {_one_line(item.get('error'), limit=220)}")
    if show_boundary:
        boundary = data.get("boundary") or {}
        if boundary:
            lines.append("")
            lines.append(_section("Boundary"))
            for key in sorted(boundary):
                value = boundary[key]
                if isinstance(value, list):
                    value = ", ".join(str(item) for item in value)
                lines.append(f"  {key}: {value}")
    return "\n".join(lines)


def render_program_projection_audit_summary(data: dict[str, Any], *, show_boundary: bool = False) -> str:
    lines = [_title("Program projection run-step audit summary")]
    lines.append(f"Path: {data.get('path')}")
    lines.append(f"Program: {data.get('program_id') or '-'}  Step: {data.get('step_id') or '*'}")
    lines.append(
        "Counts: "
        f"total_lines={data.get('total_lines', 0)} · "
        f"matched={data.get('matched_lines', 0)} · "
        f"skipped={data.get('skipped_lines', 0)}"
    )
    if not data.get("exists"):
        lines.append("Audit log does not exist yet.")

    summary = data.get("summary") or {}
    if summary:
        lines.append("")
        lines.append(_section("Totals"))
        lines.append(
            "  "
            f"events={summary.get('total_events', 0)} "
            f"preview={summary.get('preview_events', 0)} "
            f"execute={summary.get('execute_events', 0)} "
            f"ok={summary.get('ok_events', 0)} "
            f"failed={summary.get('failed_events', 0)} "
            f"blocked={summary.get('blocked_events', 0)} "
            f"commands={summary.get('command_count', 0)}"
        )
        statuses = summary.get("status_counts") or {}
        if statuses:
            status_text = ", ".join(f"{key}={value}" for key, value in sorted(statuses.items()))
            lines.append(f"  statuses: {status_text}")
        if summary.get("last_event_at"):
            lines.append(
                "  last: "
                f"{summary.get('last_event_at')} "
                f"{summary.get('last_audit_id') or '-'} "
                f"step={summary.get('last_step_id') or '-'}"
            )

    steps = data.get("steps") or []
    if not steps:
        lines.append("No matching audit summary rows.")
    else:
        lines.append("")
        lines.append(_section("Steps"))
        for step in steps:
            statuses = step.get("status_counts") or {}
            status_text = ", ".join(f"{key}={value}" for key, value in sorted(statuses.items())) or "none"
            lines.append(
                f"  {step.get('step_id') or '-'}  "
                f"events={step.get('total_events', 0)} "
                f"preview={step.get('preview_events', 0)} "
                f"execute={step.get('execute_events', 0)} "
                f"failed={step.get('failed_events', 0)} "
                f"commands={step.get('command_count', 0)}"
            )
            title = _one_line(step.get("step_title"), limit=180)
            if title:
                lines.append(f"    {title}")
            lines.append(f"    statuses: {status_text}")
            if step.get("last_event_at"):
                lines.append(f"    last={step.get('last_event_at')} audit_id={step.get('last_audit_id') or '-'}")

    skipped = data.get("skipped") or []
    if skipped:
        lines.append("")
        lines.append(_section("Skipped malformed lines"))
        for item in skipped:
            lines.append(f"  line {item.get('line_number')}: {_one_line(item.get('error'), limit=220)}")
    if show_boundary:
        boundary = data.get("boundary") or {}
        if boundary:
            lines.append("")
            lines.append(_section("Boundary"))
            for key in sorted(boundary):
                value = boundary[key]
                if isinstance(value, list):
                    value = ", ".join(str(item) for item in value)
                lines.append(f"  {key}: {value}")
    return "\n".join(lines)

def render_program_projection_run_step(data: dict[str, Any], *, show_boundary: bool = False) -> str:
    step = data.get("step") or {}
    lines = [_title("Program projection operator step")]
    lines.append(f"Program: {data.get('program_id')}")
    lines.append(f"Step: {step.get('step_id')}  [{step.get('severity')}] {step.get('title')}")
    lines.append(f"Mode: {'execute' if data.get('execute') else 'preview'}")
    reason = _one_line(step.get("reason"), limit=260)
    if reason:
        lines.append(f"Reason: {reason}")

    results = data.get("results") or []
    if not results:
        lines.append("No commands selected.")
    else:
        lines.append("")
        lines.append(_section("Commands"))
        for index, result in enumerate(results, start=1):
            marker = result.get("status") or "unknown"
            lines.append(f"  {index}. [{marker}] $ {result.get('command')}")
            if result.get("returncode") is not None:
                lines.append(f"     returncode={result.get('returncode')}")
            if result.get("error"):
                lines.append(f"     error={_one_line(result.get('error'), limit=260)}")
            stdout = _one_line(result.get("stdout"), limit=220)
            stderr = _one_line(result.get("stderr"), limit=220)
            if stdout:
                lines.append(f"     stdout: {stdout}")
            if stderr:
                lines.append(f"     stderr: {stderr}")

    audit = data.get("audit") or {}
    if audit.get("enabled"):
        lines.append("")
        lines.append(_section("Audit"))
        lines.append(f"  audit_id={audit.get('audit_id')}")
        lines.append(f"  path={audit.get('path')}")
    elif audit:
        lines.append("")
        lines.append(_section("Audit"))
        lines.append("  disabled")

    if not data.get("execute"):
        lines.append("")
        lines.append("Preview only. Add --execute --yes to run this exact step.")

    if show_boundary:
        boundary = data.get("boundary") or {}
        if boundary:
            lines.append("")
            lines.append(_section("Boundary"))
            for key in sorted(boundary):
                value = boundary[key]
                if isinstance(value, list):
                    value = ", ".join(str(item) for item in value)
                lines.append(f"  {key}: {value}")
    return "\n".join(lines)


def _queue_summary(queue: dict[str, Any]) -> str:
    applied = int(queue.get('applied') or 0)
    applied_suffix = f" applied={applied}" if applied else ""
    return (
        f"pending={queue.get('pending', 0)} "
        f"locked={queue.get('locked', 0)} "
        f"failed={queue.get('failed', 0)} "
        f"dead={queue.get('dead', 0)} "
        f"processed={queue.get('processed', 0)}"
        f"{applied_suffix}"
    )


def _bool_mark(value: Any) -> str:
    return "ok" if bool(value) else "stale"


def _render_usage(usage: dict[str, Any]) -> list[str]:
    if not usage:
        return []
    lines = []
    selected = usage.get("selected_modes") or {}
    if selected:
        parts = [f"{mode}={selected.get(mode, 0)}" for mode in ("none", "cheap", "normal", "deep")]
        lines.append("Agent runtime: " + " · ".join(parts))
    warnings = usage.get("warnings") or []
    if warnings:
        lines.append("Runtime warnings: " + ", ".join(str(item) for item in warnings[:4]))
    return lines


def _proposal_line(proposal: dict[str, Any]) -> str:
    return (
        f"  {proposal.get('proposal_id')}  [{proposal.get('status')}] "
        f"{proposal.get('priority')}/{proposal.get('risk_level')}  "
        f"{proposal.get('agent_key')}: {proposal.get('title')}"
    )


def _experience_proposal_line(proposal: dict[str, Any]) -> str:
    return (
        f"  {proposal.get('proposal_id')}  [{proposal.get('status')}] "
        f"rank={proposal.get('rank')} score={proposal.get('utility_score')} "
        f"{proposal.get('capability_id')}/{proposal.get('profile_id')} "
        f"samples={proposal.get('sample_count')} sim={proposal.get('avg_similarity')}"
    )


def _one_line(value: Any, *, limit: int = 180) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _title(value: str) -> str:
    return f"== {value} =="


def _section(value: str) -> str:
    return f"-- {value} --"


def render_worker_once(payload: dict[str, Any]) -> str:
    worker = payload.get("worker") or payload
    lines = [_title("Agent worker run-once")]
    lines.extend(_render_worker(worker))
    return "\n".join(lines)


def render_task_run_agent(payload: dict[str, Any]) -> str:
    created = payload.get("created") or {}
    detail = payload.get("task_detail") or {}
    task = (created.get("task") or {}) or (detail.get("task") or {})
    messages = detail.get("messages") or []
    proposals = detail.get("proposals") or []
    lines = [_title("Agent task run")]
    if task:
        lines.append(f"Task: {task.get('task_id')}  Agent: {task.get('target_agent')}  Status: {task.get('status')}")
    else:
        lines.append("Task: -")
    prompt = _one_line((created.get("first_message") or {}).get("body") or task.get("prompt_excerpt"), limit=300)
    if prompt:
        lines.append(f"Prompt: {prompt}")
    lines.append("")
    lines.append(_section("Worker"))
    lines.extend(_render_worker(payload.get("worker") or {}))
    lines.append("")
    lines.append(_section("Latest thread"))
    if not messages:
        lines.append("  No thread messages yet.")
    for message in messages[-6:]:
        prefix = f"{message.get('role')}"
        if message.get("agent_key"):
            prefix += f"/{message.get('agent_key')}"
        prefix += f"/{message.get('message_kind')}"
        lines.append(f"  {prefix}: {_one_line(message.get('body'), limit=360)}")
    lines.append("")
    lines.append(_section("Proposals"))
    if not proposals:
        lines.append("  No proposals yet. If the worker processed 0 messages, run: bb task run-agent")
    for proposal in proposals[:10]:
        lines.append(_proposal_line(proposal))
        summary = _one_line(proposal.get("summary"), limit=240)
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

def _render_worker(worker: dict[str, Any]) -> list[str]:
    if not worker:
        return ["  Worker result is missing."]
    status = worker.get("status")
    command = " ".join(str(part) for part in (worker.get("command") or [])) or "-"
    lines = [f"  Status: {status}  Exit: {worker.get('exit_code')}  Command: {command}"]
    stdout = _one_line(worker.get("stdout"), limit=500)
    stderr = _one_line(worker.get("stderr"), limit=500)
    if stdout:
        lines.append(f"  stdout: {stdout}")
    if stderr:
        lines.append(f"  stderr: {stderr}")
    if worker.get("skipped"):
        lines.append("  skipped: task was created; worker was not invoked")
    return lines
