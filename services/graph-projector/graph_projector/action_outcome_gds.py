from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Protocol


class Neo4jSession(Protocol):
    def run(self, query: str, parameters: dict[str, object] | None = None) -> Any: ...


@dataclass(frozen=True)
class ActionOutcomeGdsCandidate:
    capability_id: str
    profile_id: str
    sample_count: int
    avg_similarity: float
    avg_information_gain_score: float
    human_positive_rate: float
    human_stop_rate: float
    utility_score: float
    rank_score: float | None = None
    base_utility_score: float | None = None
    adjusted_rank_score: float | None = None
    review_prior_multiplier: float = 1.0
    review_prior_formula_version: str | None = None
    rank_score_semantics: str = "outcome-derived utility rank score"


class ActionOutcomeGdsUtilityReader:
    """Read action utility from Neo4j GDS over outcome-feature similarity.

    This reader intentionally operates on the graph projection produced from
    ActionOutcome memory. It avoids SQL cohorts and vulnerability labels: GDS
    compares outcomes by shared generic OutcomeFeature nodes, then aggregates
    candidate capability/profile utility from similar past outcomes.
    """

    def rank_capability_profiles(
        self,
        session: Neo4jSession,
        *,
        program_id: str,
        seed_outcome_id: str,
        graph_name: str = "action_outcome_utility",
        limit: int = 25,
        similarity_cutoff: float = 0.1,
    ) -> tuple[ActionOutcomeGdsCandidate, ...]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if not 0 <= similarity_cutoff <= 1:
            raise ValueError("similarity_cutoff must be between 0 and 1")
        safe_graph_name = _safe_graph_name(graph_name)
        parameters = {
            "program_id": program_id,
            "seed_outcome_id": seed_outcome_id,
            "graph_name": safe_graph_name,
            "limit": limit,
            "similarity_cutoff": similarity_cutoff,
        }
        rows = session.run(ACTION_OUTCOME_GDS_UTILITY_CYPHER, parameters)
        return tuple(_candidate_from_row(dict(row)) for row in rows)

    def rank_capability_profiles_for_probe(
        self,
        session: Neo4jSession,
        *,
        program_id: str,
        feature_keys: Iterable[str],
        probe_id: str | None = None,
        graph_name: str = "action_experience_probe",
        limit: int = 25,
        similarity_cutoff: float = 0.1,
        candidate_profile_limit: int = 100,
    ) -> tuple[ActionOutcomeGdsCandidate, ...]:
        """Rank capability/profile pairs for a state plus candidate action.

        The query builds one feature-key set per historical CapabilityProfile
        and compares it with historical state+action outcomes via Jaccard overlap.
        It does not write transient probe nodes into Neo4j, so candidate ranking
        remains a read-only scoring path.

        ``graph_name`` and ``probe_id`` are deprecated compatibility parameters
        from the former GDS probe implementation. They are validated only and do
        not participate in the read-only Jaccard query.
        """

        if limit <= 0:
            raise ValueError("limit must be positive")
        if not 0 <= similarity_cutoff <= 1:
            raise ValueError("similarity_cutoff must be between 0 and 1")
        if candidate_profile_limit <= 0:
            raise ValueError("candidate_profile_limit must be positive")
        _safe_graph_name(graph_name)
        normalized_feature_keys = _normalize_feature_keys(feature_keys)
        if probe_id is not None:
            _safe_probe_id(probe_id)
        parameters = {
            "program_id": program_id,
            "feature_keys": list(normalized_feature_keys),
            "limit": limit,
            "similarity_cutoff": similarity_cutoff,
            "candidate_profile_limit": candidate_profile_limit,
        }
        rows = session.run(ACTION_EXPERIENCE_PROBE_GDS_CYPHER, parameters)
        return tuple(_candidate_from_row(dict(row)) for row in rows)


ACTION_OUTCOME_GDS_UTILITY_CYPHER = """
MATCH (seed:ActionOutcome {program_id: $program_id, outcome_id: $seed_outcome_id})
WITH seed
CALL gds.graph.project.cypher(
  $graph_name,
  'MATCH (n) WHERE n.program_id = $program_id AND (n:ActionOutcome OR n:OutcomeFeature) RETURN id(n) AS id',
  'MATCH (o:ActionOutcome {program_id: $program_id})-[:HAS_OUTCOME_FEATURE]->(f:OutcomeFeature {program_id: $program_id}) RETURN id(o) AS source, id(f) AS target UNION MATCH (o:ActionOutcome {program_id: $program_id})-[:HAS_OUTCOME_FEATURE]->(f:OutcomeFeature {program_id: $program_id}) RETURN id(f) AS source, id(o) AS target',
  {parameters: {program_id: $program_id}}
)
YIELD graphName
CALL gds.nodeSimilarity.stream(graphName, {similarityCutoff: $similarity_cutoff})
YIELD node1, node2, similarity
WITH seed, graphName, gds.util.asNode(node1) AS a, gds.util.asNode(node2) AS b, similarity
WITH seed, graphName,
     CASE WHEN a.outcome_id = seed.outcome_id THEN b ELSE a END AS similar_outcome,
     similarity
WHERE similar_outcome:ActionOutcome
  AND similar_outcome.program_id = $program_id
  AND similar_outcome.outcome_id <> seed.outcome_id
MATCH (similar_outcome)-[:USED_CAPABILITY_PROFILE]->(profile:CapabilityProfile {program_id: $program_id})
WITH graphName,
     profile.capability_id AS capability_id,
     profile.profile_id AS profile_id,
     count(similar_outcome) AS sample_count,
     avg(similarity) AS avg_similarity,
     avg(coalesce(similar_outcome.information_gain_score, 0.0)) AS avg_information_gain_score,
     avg(CASE WHEN coalesce(similar_outcome.manual_interest, false) OR coalesce(similar_outcome.continued_by_followup, false) OR coalesce(similar_outcome.report_created, false) THEN 1.0 ELSE 0.0 END) AS human_positive_rate,
     avg(CASE WHEN coalesce(similar_outcome.manual_stop, false) THEN 1.0 ELSE 0.0 END) AS human_stop_rate
WITH graphName,
     capability_id,
     profile_id,
     sample_count,
     avg_similarity,
     avg_information_gain_score,
     human_positive_rate,
     human_stop_rate,
     (avg_information_gain_score * avg_similarity * (1.0 + human_positive_rate)) / (1.0 + human_stop_rate) AS utility_score
CALL gds.graph.drop(graphName, false) YIELD graphName AS droppedGraphName
RETURN capability_id,
       profile_id,
       sample_count,
       avg_similarity,
       avg_information_gain_score,
       human_positive_rate,
       human_stop_rate,
       utility_score
ORDER BY utility_score DESC, sample_count DESC
LIMIT $limit
""".strip()


ACTION_EXPERIENCE_PROBE_GDS_CYPHER = """
MATCH (profile:CapabilityProfile {program_id: $program_id})
WITH collect(profile)[0..$candidate_profile_limit] AS profiles
UNWIND profiles AS profile
WITH profile,
     $feature_keys
       + ['capability:' + profile.capability_id]
       + ['profile:' + profile.profile_id]
       + ['capability_profile:' + profile.profile_key] AS requested_feature_keys
OPTIONAL MATCH (probe_feature:OutcomeFeature {program_id: $program_id})
WHERE probe_feature.key IN requested_feature_keys
WITH profile,
     collect(DISTINCT probe_feature.key) AS probe_feature_keys
MATCH (similar_outcome:ActionOutcome {program_id: $program_id})-[:HAS_OUTCOME_FEATURE]->(outcome_feature:OutcomeFeature {program_id: $program_id})
WHERE similar_outcome.capability_id = profile.capability_id
  AND similar_outcome.profile_id = profile.profile_id
WITH profile,
     probe_feature_keys,
     similar_outcome,
     collect(DISTINCT outcome_feature.key) AS outcome_feature_keys
WITH profile,
     similar_outcome,
     size([feature_key IN probe_feature_keys WHERE feature_key IN outcome_feature_keys]) AS intersection_size,
     size(probe_feature_keys + [feature_key IN outcome_feature_keys WHERE NOT (feature_key IN probe_feature_keys)]) AS union_size
WITH profile,
     similar_outcome,
     CASE WHEN union_size = 0 THEN 0.0 ELSE toFloat(intersection_size) / toFloat(union_size) END AS similarity
WHERE similarity >= $similarity_cutoff
WITH profile.capability_id AS capability_id,
     profile.profile_id AS profile_id,
     count(similar_outcome) AS sample_count,
     avg(similarity) AS avg_similarity,
     avg(coalesce(similar_outcome.information_gain_score, 0.0)) AS avg_information_gain_score,
     avg(CASE WHEN coalesce(similar_outcome.manual_interest, false) OR coalesce(similar_outcome.continued_by_followup, false) OR coalesce(similar_outcome.report_created, false) THEN 1.0 ELSE 0.0 END) AS human_positive_rate,
     avg(CASE WHEN coalesce(similar_outcome.manual_stop, false) THEN 1.0 ELSE 0.0 END) AS human_stop_rate
WITH capability_id,
     profile_id,
     sample_count,
     avg_similarity,
     avg_information_gain_score,
     human_positive_rate,
     human_stop_rate,
     (toFloat(sample_count) / (toFloat(sample_count) + 5.0)) AS confidence_score
WITH capability_id,
     profile_id,
     sample_count,
     avg_similarity,
     avg_information_gain_score,
     human_positive_rate,
     human_stop_rate,
     (avg_information_gain_score * avg_similarity * confidence_score * (1.0 + human_positive_rate)) / (1.0 + human_stop_rate) AS utility_score
RETURN capability_id,
       profile_id,
       sample_count,
       avg_similarity,
       avg_information_gain_score,
       human_positive_rate,
       human_stop_rate,
       utility_score
ORDER BY utility_score DESC, sample_count DESC
LIMIT $limit
""".strip()


def _candidate_from_row(row: Mapping[str, Any]) -> ActionOutcomeGdsCandidate:
    return ActionOutcomeGdsCandidate(
        capability_id=str(row["capability_id"]),
        profile_id=str(row["profile_id"]),
        sample_count=int(row.get("sample_count") or 0),
        avg_similarity=float(row.get("avg_similarity") or 0.0),
        avg_information_gain_score=float(row.get("avg_information_gain_score") or 0.0),
        human_positive_rate=float(row.get("human_positive_rate") or 0.0),
        human_stop_rate=float(row.get("human_stop_rate") or 0.0),
        utility_score=float(row.get("utility_score") or 0.0),
    )


def _normalize_feature_keys(feature_keys: Iterable[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in feature_keys:
        text = str(value).strip()
        if not text:
            continue
        if text not in seen:
            normalized.append(text)
            seen.add(text)
    if not normalized:
        raise ValueError("feature_keys must contain at least one non-empty feature key")
    if len(normalized) > 128:
        raise ValueError("feature_keys must contain at most 128 items")
    return tuple(normalized)


def _safe_graph_name(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_:-]{0,100}", value):
        raise ValueError(f"unsafe GDS graph name: {value}")
    return value


def _safe_probe_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", value):
        raise ValueError(f"unsafe probe id: {value}")
    return value
