"""Utility functions for extracting normalized targets from events."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

_TARGET_KEYS = (
    "raw_domains",
    "subdomains",
    "hostnames",
    "urls",
    "hosts",
    "ips",
    "targets",
)
_VALUE_KEYS = (
    "target",
    "url",
    "host",
    "domain",
    "hostname",
    "ip",
    "value",
    "name",
)


def default_target_extractor(event: Mapping[str, Any]) -> list[str]:
    """
    Extract targets from common event fields and normalize them to strings.

    Event producers are not perfectly uniform: direct actions, pipeline events,
    graph nodes, and older adapters can emit a scalar target, a list, a nested
    list, or a small object such as {"host": "example.com"}. Scan runners must
    never receive these raw shapes. They receive a flat list[str].
    """
    for key in _TARGET_KEYS:
        value = event.get(key)
        if value:
            return normalize_targets(value)
    return []


def normalize_targets(value: Any) -> list[str]:
    """Return a stable, flat, non-empty list of target strings."""
    normalized: list[str] = []
    seen: set[str] = set()
    for target in _iter_target_values(value):
        text = str(target).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def _iter_target_values(value: Any):
    if value is None:
        return
    if isinstance(value, str):
        for item in value.splitlines():
            text = item.strip()
            if text:
                yield text
        return
    if isinstance(value, bytes):
        text = value.decode(errors="ignore").strip()
        if text:
            yield text
        return
    if isinstance(value, Mapping):
        for key in _VALUE_KEYS:
            if key in value and value[key]:
                yield from _iter_target_values(value[key])
                return
        return
    if isinstance(value, Iterable):
        for item in value:
            yield from _iter_target_values(item)
        return
    yield value
