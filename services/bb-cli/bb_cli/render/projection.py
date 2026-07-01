from __future__ import annotations

from typing import Any

from .common import append_boundary, bool_mark, one_line, queue_summary, section, title


def render_program_projection_overview(data: dict[str, Any], *, show_boundary: bool = False) -> str:
    lines = [title("Program projection overview")]
    lines.append(f"Program: {data.get('program_id')}")
    lines.append(
        "Freshness: "
        f"surface_analysis={bool_mark(data.get('surface_analysis_fresh'))} · "
        f"search_index={bool_mark(data.get('search_index_fresh'))} · "
        f"ui_data={bool_mark(data.get('ui_data_fresh'))}"
    )

    snapshot = data.get("latest_surface_snapshot") or {}
    analysis = data.get("latest_surface_analysis") or {}
    lines.append("")
    lines.append(section("Surface state"))
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
    lines.append(section("Durable queues"))
    queue_names = [
        ("Graph projection events", "graph_projection_events"),
        ("Graph fact batches", "graph_fact_batches"),
        ("Surface analysis events", "surface_analysis_events"),
        ("Search projection events", "search_projection_events"),
    ]
    for label, key in queue_names:
        lines.append(f"  {label}: {queue_summary(data.get(key) or {})}")

    search = data.get("search_index") or {}
    lines.append("")
    lines.append(section("Search index"))
    lines.append(
        "  Components indexed: "
        f"{bool_mark(search.get('surface_components_indexed'))}  "
        f"status={search.get('latest_surface_components_event_status') or '-'}"
    )
    lines.append(
        "  Deltas indexed: "
        f"{bool_mark(search.get('surface_deltas_indexed'))}  "
        f"status={search.get('latest_surface_deltas_event_status') or '-'}"
    )

    proposals = data.get("experience_proposals") or {}
    lines.append("")
    lines.append(section("Action experience proposals"))
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
        lines.append(section("Suggested commands"))
        for command in commands[:10]:
            lines.append(f"  {command}")

    if show_boundary:
        append_boundary(lines, data.get("boundary") or {})
    return "\n".join(lines)


def render_program_projection_plan(data: dict[str, Any], *, show_boundary: bool = False) -> str:
    lines = [title("Program projection operator plan")]
    lines.append(f"Program: {data.get('program_id')}")
    lines.append(f"UI data fresh: {bool_mark(data.get('ui_data_fresh'))}")
    lines.append(f"Steps: {data.get('step_count', 0)}")

    steps = data.get("steps") or []
    if not steps:
        lines.append("No operator steps returned.")
    else:
        lines.append("")
        lines.append(section("Ordered steps"))
        for step in steps:
            lines.append(
                "  "
                f"{step.get('priority')}. [{step.get('severity')}] "
                f"{step.get('area')}: {step.get('title')}"
            )
            reason = one_line(step.get("reason"), limit=260)
            if reason:
                lines.append(f"     Reason: {reason}")
            for command in step.get("commands") or []:
                lines.append(f"     $ {command}")

    if show_boundary:
        append_boundary(lines, data.get("boundary") or {})
    return "\n".join(lines)


def render_program_projection_audit(data: dict[str, Any], *, show_boundary: bool = False) -> str:
    lines = [title("Program projection run-step audit")]
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
        lines.append(section("Events"))
        for event in events:
            mode = "execute" if event.get("execute") else "preview"
            statuses = event.get("statuses") or {}
            status_text = ", ".join(f"{key}={value}" for key, value in sorted(statuses.items())) or "none"
            lines.append(
                f"  {event.get('created_at') or '-'}  {event.get('audit_id') or '-'}  "
                f"[{mode}] {event.get('step_id') or '-'}  commands={event.get('command_count', 0)}  {status_text}"
            )
            step_title = one_line(event.get("step_title"), limit=180)
            if step_title:
                lines.append(f"    {step_title}")
            commands = event.get("commands") or []
            for command in commands[:3]:
                lines.append(f"    $ {command}")
            if len(commands) > 3:
                lines.append(f"    ... {len(commands) - 3} more command(s)")
    skipped = data.get("skipped") or []
    if skipped:
        lines.append("")
        lines.append(section("Skipped malformed lines"))
        for item in skipped:
            lines.append(f"  line {item.get('line_number')}: {one_line(item.get('error'), limit=220)}")
    if show_boundary:
        append_boundary(lines, data.get("boundary") or {})
    return "\n".join(lines)


def render_program_projection_audit_summary(data: dict[str, Any], *, show_boundary: bool = False) -> str:
    lines = [title("Program projection run-step audit summary")]
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
        lines.append(section("Totals"))
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
        lines.append(section("Steps"))
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
            step_title = one_line(step.get("step_title"), limit=180)
            if step_title:
                lines.append(f"    {step_title}")
            lines.append(f"    statuses: {status_text}")
            if step.get("last_event_at"):
                lines.append(f"    last={step.get('last_event_at')} audit_id={step.get('last_audit_id') or '-'}")

    skipped = data.get("skipped") or []
    if skipped:
        lines.append("")
        lines.append(section("Skipped malformed lines"))
        for item in skipped:
            lines.append(f"  line {item.get('line_number')}: {one_line(item.get('error'), limit=220)}")
    if show_boundary:
        append_boundary(lines, data.get("boundary") or {})
    return "\n".join(lines)


def render_program_projection_run_step(data: dict[str, Any], *, show_boundary: bool = False) -> str:
    step = data.get("step") or {}
    lines = [title("Program projection operator step")]
    lines.append(f"Program: {data.get('program_id')}")
    lines.append(f"Step: {step.get('step_id')}  [{step.get('severity')}] {step.get('title')}")
    lines.append(f"Mode: {'execute' if data.get('execute') else 'preview'}")
    reason = one_line(step.get("reason"), limit=260)
    if reason:
        lines.append(f"Reason: {reason}")

    results = data.get("results") or []
    if not results:
        lines.append("No commands selected.")
    else:
        lines.append("")
        lines.append(section("Commands"))
        for index, result in enumerate(results, start=1):
            marker = result.get("status") or "unknown"
            lines.append(f"  {index}. [{marker}] $ {result.get('command')}")
            if result.get("returncode") is not None:
                lines.append(f"     returncode={result.get('returncode')}")
            if result.get("error"):
                lines.append(f"     error={one_line(result.get('error'), limit=260)}")
            stdout = one_line(result.get("stdout"), limit=220)
            stderr = one_line(result.get("stderr"), limit=220)
            if stdout:
                lines.append(f"     stdout: {stdout}")
            if stderr:
                lines.append(f"     stderr: {stderr}")

    audit = data.get("audit") or {}
    if audit.get("enabled"):
        lines.append("")
        lines.append(section("Audit"))
        lines.append(f"  audit_id={audit.get('audit_id')}")
        lines.append(f"  path={audit.get('path')}")
    elif audit:
        lines.append("")
        lines.append(section("Audit"))
        lines.append("  disabled")

    if not data.get("execute"):
        lines.append("")
        lines.append("Preview only. Add --execute --yes to run this exact step.")

    if show_boundary:
        append_boundary(lines, data.get("boundary") or {})
    return "\n".join(lines)
