from __future__ import annotations

from typing import Any

from .common import one_line, title


def render_activity(snapshot: dict[str, Any]) -> str:
    lines = [title("Agent activity")]
    events = snapshot.get("events") or snapshot.get("items") or []
    if not events:
        lines.append("No activity events.")
        return "\n".join(lines)
    for event in events:
        lines.append(
            f"{event.get('created_at') or event.get('timestamp') or '-'}  "
            f"{event.get('event_type') or event.get('type')}: "
            f"{one_line(event.get('title') or event.get('body') or event.get('summary'), limit=220)}"
        )
    next_after = snapshot.get("next_after")
    if next_after:
        lines.append("")
        lines.append(f"Next cursor: {next_after}")
    return "\n".join(lines)
