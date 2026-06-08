"""Stable fingerprints for pipeline node responsibility claims."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Any
from uuid import UUID


TRANSPORT_KEYS = {
    "event_id",
    "job_id",
    "run_id",
    "correlation_id",
    "causation_id",
    "confidence",
    "source",
    "created_at",
}


def build_node_input_fingerprint(node_id: str, event: dict[str, Any]) -> str:
    """Hash execution-relevant event inputs for a specific node."""
    execution_input = {
        key: value for key, value in event.items() if key not in TRANSPORT_KEYS
    }
    if "targets" in execution_input:
        execution_input["targets"] = _normalized_targets(execution_input["targets"])
    elif "target" in execution_input:
        execution_input["target"] = str(execution_input["target"]).strip()

    return _sha256_json(
        {
            "node_id": node_id,
            "input": execution_input,
        }
    )


def build_target_fingerprint(targets: list[Any] | tuple[Any, ...] | None) -> str:
    """Hash target identity independently from list ordering."""
    return _sha256_json({"targets": _normalized_targets(targets or [])})


def build_node_claim_key(
    *,
    trigger_event_id: UUID,
    node_id: str,
    input_fingerprint: str,
) -> str:
    """Hash the durable responsibility key for one trigger event and node input."""
    return _sha256_json(
        {
            "trigger_event_id": str(trigger_event_id),
            "node_id": node_id,
            "input_fingerprint": input_fingerprint,
        }
    )


def _normalized_targets(targets: list[Any] | tuple[Any, ...]) -> list[str]:
    return sorted({str(target).strip() for target in targets if str(target).strip()})


def _sha256_json(value: Any) -> str:
    encoded = json.dumps(
        _json_safe(value),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _json_safe(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return value
