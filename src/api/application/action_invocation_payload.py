"""Shared action invocation payload helpers.

Initial action events carry runner invocation data under one nested payload key.
Legacy events may still expose the same values directly in the envelope payload
or as top-level legacy fields after EventEnvelope.to_legacy_dict().
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

ACTION_INVOCATION_PAYLOAD_KEY = "action_invocation"
ACTION_INVOCATION_SCHEMA = "action-invocation-v1"


def action_invocation_mapping(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return nested action invocation data when present, otherwise an empty mapping."""
    nested = payload.get(ACTION_INVOCATION_PAYLOAD_KEY)
    return nested if isinstance(nested, Mapping) else {}


def action_invocation_value(payload: Mapping[str, Any], key: str) -> Any:
    """Return an action invocation value from nested v1 payload or legacy payload."""
    nested = action_invocation_mapping(payload)
    if key in nested:
        return nested[key]
    return payload.get(key)
