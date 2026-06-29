from __future__ import annotations

from typing import Any, Mapping
from uuid import UUID

from .proposal_row_codec import _optional_int, _optional_text, _optional_uuid, _required_uuid


def _source_values(source: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "program_id": _required_uuid(source, "program_id"),
        "campaign_id": _optional_uuid(source.get("campaign_id")),
        "source_outcome_id": _required_uuid(source, "id"),
        "source_action_id": _required_uuid(source, "action_id"),
        "source_job_id": _required_uuid(source, "job_id"),
        "source_run_id": _required_uuid(source, "run_id"),
    }


def _source_probe_feature_keys(source: Mapping[str, Any]) -> tuple[str, ...]:
    """Build bounded state features from the completed source outcome row.

    These are not bug/domain rules. They are execution/state shape features that
    allow the GDS reader to rank candidate actions as state+candidate pairs.
    """

    features: list[str] = []
    status = _optional_text(source.get("status"))
    if status:
        features.append(f"status:{status}")
    terminal_outcome = _optional_text(source.get("terminal_outcome"))
    if terminal_outcome:
        features.append(f"terminal_outcome:{terminal_outcome}")
    target_count = _optional_int(source.get("target_count"))
    if target_count is not None:
        features.append(f"target_count_bucket:{_count_bucket(target_count)}")
    duration_ms = _optional_int(source.get("duration_ms"))
    if duration_ms is not None:
        features.append(f"duration_bucket:{_duration_bucket(duration_ms)}")
    for source_key, feature_name in (
        ("raw_artifact_count", "raw_artifact_bucket"),
        ("http_observation_count", "http_observation_bucket"),
        ("javascript_reference_count", "javascript_reference_bucket"),
        ("error_count", "error_bucket"),
    ):
        value = _optional_int(source.get(source_key))
        if value is not None:
            features.append(f"{feature_name}:{_count_bucket(value)}")
    observation_count = _optional_int(source.get("http_observation_count")) or 0
    observation_count += _optional_int(source.get("javascript_reference_count")) or 0
    if observation_count:
        features.append(f"observation_bucket:{_count_bucket(observation_count)}")
    if source.get("manual_interest") is True:
        features.append("human_signal:manual_interest")
    if source.get("manual_stop") is True:
        features.append("human_signal:manual_stop")
    if source.get("continued_by_followup") is True:
        features.append("human_signal:continued_by_followup")
    if source.get("report_created") is True:
        features.append("human_signal:report_created")
    triage_outcome = _optional_text(source.get("triage_outcome"))
    if triage_outcome:
        features.append(f"triage_outcome:{triage_outcome}")
    return _dedupe_texts(features)

def _dedupe_texts(values: list[str]) -> tuple[str, ...]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = value.strip()
        if text and text not in seen:
            deduped.append(text)
            seen.add(text)
    return tuple(deduped)


def _count_bucket(value: int) -> str:
    if value <= 0:
        return "0"
    if value == 1:
        return "1"
    if value <= 5:
        return "2-5"
    if value <= 20:
        return "6-20"
    if value <= 100:
        return "21-100"
    return "100+"


def _duration_bucket(value: int | None) -> str:
    if value is None:
        return "unknown"
    if value <= 1000:
        return "<=1s"
    if value <= 10_000:
        return "1s-10s"
    if value <= 60_000:
        return "10s-60s"
    if value <= 300_000:
        return "1m-5m"
    return "5m+"
