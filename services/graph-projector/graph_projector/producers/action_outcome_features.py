from __future__ import annotations

from .action_outcome_projection import ActionOutcomeProjection



def outcome_features(projection: ActionOutcomeProjection) -> tuple[tuple[str, str], ...]:
    features: list[tuple[str, str]] = [
        ("capability", projection.capability_id),
        ("profile", projection.profile_id),
        ("capability_profile", projection.profile_key),
        ("status", projection.status),
        ("target_count_bucket", count_bucket(projection.target_count or 0)),
        ("duration_bucket", duration_bucket(projection.duration_ms)),
        ("raw_artifact_bucket", count_bucket(projection.raw_artifact_count)),
        ("http_observation_bucket", count_bucket(projection.http_observation_count)),
        ("javascript_reference_bucket", count_bucket(projection.javascript_reference_count)),
        ("observation_bucket", count_bucket(projection.observation_count)),
        ("surface_hosts_bucket", count_bucket(projection.observed_hosts_count)),
        ("surface_services_bucket", count_bucket(projection.observed_services_count)),
        ("surface_endpoints_bucket", count_bucket(projection.observed_endpoints_count)),
        ("error_bucket", count_bucket(projection.error_count)),
        ("information_gain_bucket", score_bucket(projection.information_gain_score)),
    ]
    if projection.node_id:
        features.append(("node", projection.node_id))
    if projection.event_name:
        features.append(("event", projection.event_name))
    if projection.terminal_outcome:
        features.append(("terminal_outcome", projection.terminal_outcome))
    if projection.manual_interest is True:
        features.append(("human_signal", "manual_interest"))
    if projection.manual_stop is True:
        features.append(("human_signal", "manual_stop"))
    if projection.continued_by_followup is True:
        features.append(("human_signal", "continued_by_followup"))
    if projection.report_created is True:
        features.append(("human_signal", "report_created"))
    if projection.triage_outcome:
        features.append(("triage_outcome", projection.triage_outcome))
    return tuple(features)



def count_bucket(value: int) -> str:
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



def duration_bucket(value: int | None) -> str:
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



def score_bucket(value: float) -> str:
    if value <= 0:
        return "0"
    if value < 1:
        return "0-1"
    if value < 5:
        return "1-5"
    if value < 20:
        return "5-20"
    return "20+"
