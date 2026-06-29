from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping
from uuid import UUID

from ..row_codec import (
    optional_int,
    optional_text,
    optional_uuid_text,
    required_row_text,
    required_row_uuid,
)


@dataclass(frozen=True)
class ActionOutcomeProjection:
    program_id: UUID
    outcome_id: UUID
    run_id: UUID
    capability_id: str
    profile_id: str
    status: str
    action_id: str | None
    job_id: str | None
    campaign_id: str | None
    node_id: str | None
    event_name: str | None
    terminal_outcome: str | None
    started_at: datetime | None
    finished_at: datetime | None
    updated_at: datetime | None
    before_surface_snapshot_id: str | None
    after_surface_snapshot_id: str | None
    raw_artifact_count: int
    http_observation_count: int
    javascript_reference_count: int
    observed_hosts_count: int
    observed_services_count: int
    observed_endpoints_count: int
    duration_ms: int | None
    error_count: int
    information_gain_score: float
    target_count: int | None
    score_version: str | None
    manual_interest: bool | None
    manual_stop: bool | None
    continued_by_followup: bool | None
    report_created: bool | None
    triage_outcome: str | None

    @property
    def profile_key(self) -> str:
        return f"{self.capability_id}:{self.profile_id}"

    @property
    def observation_count(self) -> int:
        return self.http_observation_count + self.javascript_reference_count



def action_outcome_projection_from_row(row: Mapping[str, Any]) -> ActionOutcomeProjection:
    return ActionOutcomeProjection(
        program_id=required_row_uuid(row, "program_id", context="action_outcome"),
        outcome_id=required_row_uuid(row, "id", context="action_outcome"),
        run_id=required_row_uuid(row, "run_id", context="action_outcome"),
        capability_id=required_row_text(row, "capability_id", context="action_outcome"),
        profile_id=required_row_text(row, "profile_id", context="action_outcome"),
        status=required_row_text(row, "status", context="action_outcome"),
        action_id=optional_uuid_text(row.get("action_id")),
        job_id=optional_uuid_text(row.get("job_id")),
        campaign_id=optional_uuid_text(row.get("campaign_id")),
        node_id=optional_text(row.get("node_id")),
        event_name=optional_text(row.get("event_name")),
        terminal_outcome=optional_text(row.get("terminal_outcome")),
        started_at=optional_datetime(row.get("started_at")),
        finished_at=optional_datetime(row.get("finished_at")),
        updated_at=optional_datetime(row.get("updated_at")),
        before_surface_snapshot_id=optional_uuid_text(row.get("before_surface_snapshot_id")),
        after_surface_snapshot_id=optional_uuid_text(row.get("after_surface_snapshot_id")),
        raw_artifact_count=int_value(row.get("raw_artifact_count")),
        http_observation_count=int_value(row.get("http_observation_count")),
        javascript_reference_count=int_value(row.get("javascript_reference_count")),
        observed_hosts_count=int_value(row.get("observed_hosts_count")),
        observed_services_count=int_value(row.get("observed_services_count")),
        observed_endpoints_count=int_value(row.get("observed_endpoints_count")),
        duration_ms=optional_int(row.get("duration_ms")),
        error_count=int_value(row.get("error_count")),
        information_gain_score=float_value(row.get("information_gain_score")),
        target_count=optional_int(row.get("target_count")),
        score_version=optional_text(row.get("score_version")),
        manual_interest=optional_bool(row.get("manual_interest")),
        manual_stop=optional_bool(row.get("manual_stop")),
        continued_by_followup=optional_bool(row.get("continued_by_followup")),
        report_created=optional_bool(row.get("report_created")),
        triage_outcome=optional_text(row.get("triage_outcome")),
    )



def int_value(value: Any) -> int:
    return int(value or 0)



def float_value(value: Any) -> float:
    return float(value or 0.0)



def optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    return bool(value)



def optional_datetime(value: Any) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
