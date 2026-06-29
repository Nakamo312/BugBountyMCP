from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Protocol

from .action_outcome_gds import ActionOutcomeGdsCandidate, ActionOutcomeGdsUtilityReader


class Neo4jSession(Protocol):
    def run(self, query: str, parameters: dict[str, object] | None = None) -> Any: ...


@dataclass(frozen=True)
class ActionExperienceProbeFeatureSet:
    """Generic feature keys describing the current state before candidate scoring."""

    program_id: str
    feature_keys: tuple[str, ...]
    graph_counts: Mapping[str, int]
    builder_version: str = "action-experience-probe-features.v1"


@dataclass(frozen=True)
class ActionExperienceProbeRanking:
    """Capability/profile ranking plus the probe features that produced it."""

    feature_set: ActionExperienceProbeFeatureSet
    candidates: tuple[ActionOutcomeGdsCandidate, ...]


class ActionExperienceProbeFeatureBuilder:
    """Build graph-native state features for candidate-aware probes.

    These features describe the observed state around a finished action. Candidate
    action features are added later by the utility reader as read-only feature-key
    sets, one set per capability/profile pair. The builder must not encode
    vulnerability classes or domain rules; it only emits bounded execution/context
    shape.
    """

    def build_from_graph(
        self,
        session: Neo4jSession,
        *,
        program_id: str,
        node_id: str | None = None,
        event_name: str | None = None,
        target_count: int | None = None,
        base_feature_keys: Iterable[str] = (),
    ) -> ActionExperienceProbeFeatureSet:
        if target_count is not None and target_count < 0:
            raise ValueError("target_count must not be negative")

        rows = session.run(
            ACTION_EXPERIENCE_PROBE_FEATURES_CYPHER,
            {"program_id": program_id},
        )
        row = _first_row(rows)
        counts = {
            "host_count": _int(row.get("host_count")),
            "service_count": _int(row.get("service_count")),
            "endpoint_count": _int(row.get("endpoint_count")),
            "parameter_count": _int(row.get("parameter_count")),
            "javascript_file_count": _int(row.get("javascript_file_count")),
            "outcome_count": _int(row.get("outcome_count")),
        }

        features: list[str] = []
        features.extend(_normalize_feature_keys(base_feature_keys, allow_empty=True))
        if node_id:
            features.append(f"node:{_safe_feature_value(node_id)}")
        if event_name:
            features.append(f"event:{_safe_feature_value(event_name)}")
        if target_count is not None:
            features.append(f"target_count_bucket:{_count_bucket(target_count)}")

        features.extend(
            (
                f"surface_hosts_bucket:{_count_bucket(counts['host_count'])}",
                f"surface_services_bucket:{_count_bucket(counts['service_count'])}",
                f"surface_endpoints_bucket:{_count_bucket(counts['endpoint_count'])}",
                f"javascript_reference_bucket:{_count_bucket(counts['javascript_file_count'])}",
                f"observation_bucket:{_count_bucket(counts['endpoint_count'] + counts['javascript_file_count'])}",
            )
        )
        normalized = _normalize_feature_keys(features)
        return ActionExperienceProbeFeatureSet(
            program_id=program_id,
            feature_keys=normalized,
            graph_counts=MappingProxyType(counts),
        )


class ActionExperienceProbeRanker:
    """Build current-state features and rank capability/profile choices."""

    def __init__(
        self,
        *,
        feature_builder: ActionExperienceProbeFeatureBuilder | None = None,
        utility_reader: ActionOutcomeGdsUtilityReader | None = None,
    ) -> None:
        self._feature_builder = feature_builder or ActionExperienceProbeFeatureBuilder()
        self._utility_reader = utility_reader or ActionOutcomeGdsUtilityReader()

    def rank_for_current_graph_state(
        self,
        session: Neo4jSession,
        *,
        program_id: str,
        node_id: str | None = None,
        event_name: str | None = None,
        target_count: int | None = None,
        base_feature_keys: Iterable[str] = (),
        probe_id: str | None = None,
        graph_name: str = "action_experience_probe",
        limit: int = 25,
        similarity_cutoff: float = 0.1,
        candidate_profile_limit: int = 100,
    ) -> ActionExperienceProbeRanking:
        feature_set = self._feature_builder.build_from_graph(
            session,
            program_id=program_id,
            node_id=node_id,
            event_name=event_name,
            target_count=target_count,
            base_feature_keys=base_feature_keys,
        )
        candidates = self._utility_reader.rank_capability_profiles_for_probe(
            session,
            program_id=program_id,
            probe_id=probe_id,
            feature_keys=feature_set.feature_keys,
            graph_name=graph_name,
            limit=limit,
            similarity_cutoff=similarity_cutoff,
            candidate_profile_limit=candidate_profile_limit,
        )
        return ActionExperienceProbeRanking(feature_set=feature_set, candidates=candidates)


ACTION_EXPERIENCE_PROBE_FEATURES_CYPHER = """
WITH $program_id AS program_id
CALL {
  WITH program_id
  MATCH (host:Host {program_id: program_id})
  RETURN count(host) AS host_count
}
CALL {
  WITH program_id
  MATCH (service:Service {program_id: program_id})
  RETURN count(service) AS service_count
}
CALL {
  WITH program_id
  MATCH (endpoint:Endpoint {program_id: program_id})
  RETURN count(endpoint) AS endpoint_count
}
CALL {
  WITH program_id
  MATCH (parameter:Parameter {program_id: program_id})
  RETURN count(parameter) AS parameter_count
}
CALL {
  WITH program_id
  MATCH (js:JSFile {program_id: program_id})
  RETURN count(js) AS javascript_file_count
}
CALL {
  WITH program_id
  MATCH (outcome:ActionOutcome {program_id: program_id})
  RETURN count(outcome) AS outcome_count
}
RETURN host_count,
       service_count,
       endpoint_count,
       parameter_count,
       javascript_file_count,
       outcome_count
""".strip()


def _first_row(rows: Any) -> Mapping[str, Any]:
    iterator = iter(rows)
    try:
        return dict(next(iterator))
    except StopIteration:
        return {}


def _normalize_feature_keys(feature_keys: Iterable[str], *, allow_empty: bool = False) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in feature_keys:
        text = str(value).strip()
        if not text:
            continue
        if text not in seen:
            normalized.append(text)
            seen.add(text)
    if not normalized and not allow_empty:
        raise ValueError("feature_keys must contain at least one non-empty feature key")
    if len(normalized) > 128:
        raise ValueError("feature_keys must contain at most 128 items")
    return tuple(normalized)


def _safe_feature_value(value: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError("feature value must not be empty")
    if len(text) > 160:
        raise ValueError("feature value must be at most 160 characters")
    if any(ch in text for ch in "\r\n\t"):
        raise ValueError("feature value must not contain control whitespace")
    return text


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


def _int(value: Any) -> int:
    return int(value or 0)
