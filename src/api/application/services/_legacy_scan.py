"""Compatibility helpers for legacy scan service tests."""
from __future__ import annotations

import inspect
from typing import Any


async def publish_legacy_event(bus: Any, event_type: Any, payload: dict[str, Any]) -> None:
    try:
        await bus.publish(event_type, payload)
    except TypeError:
        event_name = event_type.value if hasattr(event_type, "value") else str(event_type)
        await bus.publish({"event": event_name, **payload})


async def resolve_awaitable(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value
