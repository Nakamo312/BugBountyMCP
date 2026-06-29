"""Small sanitizers for the LangGraph-backed agent task runtime."""
from __future__ import annotations

from typing import Any


def bounded_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    safe: dict[str, Any] = {}
    for key, raw_value in list(value.items())[:20]:
        if isinstance(raw_value, dict):
            safe[str(key)[:120]] = {
                str(inner_key)[:120]: inner_value
                for inner_key, inner_value in list(raw_value.items())[:20]
                if isinstance(inner_value, (str, int, float, bool)) or inner_value is None
            }
        elif isinstance(raw_value, list):
            safe[str(key)[:120]] = bounded_dicts(raw_value, limit=8)
        elif isinstance(raw_value, (str, int, float, bool)) or raw_value is None:
            safe[str(key)[:120]] = raw_value if not isinstance(raw_value, str) else raw_value[:1000]
        else:
            safe[str(key)[:120]] = str(raw_value)[:1000]
    return safe


def bounded_dicts(value: Any, *, limit: int = 50) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in value or []:
        if not isinstance(item, dict):
            continue
        safe_item: dict[str, Any] = {}
        for key, raw_value in list(item.items())[:30]:
            if isinstance(raw_value, (str, int, float, bool)) or raw_value is None:
                safe_item[str(key)[:120]] = raw_value if not isinstance(raw_value, str) else raw_value[:1000]
            else:
                safe_item[str(key)[:120]] = str(raw_value)[:1000]
        rows.append(safe_item)
        if len(rows) >= limit:
            break
    return rows


def agent_key(value: str) -> str:
    normalized = value.strip().lower().replace(" ", "-").replace("_", "-")
    return normalized or "coordinator"


def safe_checkpoint_namespace(value: str) -> str:
    text = str(value or "agent-task").strip().lower().replace("_", "-")
    safe = "".join(ch for ch in text if ch.isalnum() or ch in {"-", ".", ":"})
    return safe[:120] or "agent-task"


def optional_uuid_text(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:1000] if text else None
