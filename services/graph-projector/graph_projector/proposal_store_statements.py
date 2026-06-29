from __future__ import annotations

ACTION_EXPERIENCE_SOURCES_WITHOUT_PROPOSAL_RUN_SQL = """
SELECT ao.*
FROM action_outcomes ao
WHERE ao.status IN ('completed', 'failed', 'dead', 'cancelled')
  AND (%(program_id)s IS NULL OR ao.program_id = %(program_id)s)
  AND NOT EXISTS (
      SELECT 1
      FROM action_experience_proposal_runs proposal_run
      WHERE proposal_run.source_outcome_id = ao.id
  )
ORDER BY ao.updated_at ASC, ao.id ASC
LIMIT %(limit)s;
""".strip()


def sources_without_proposal_run_values(*, limit: int, program_id: object | None) -> dict[str, object]:
    return {"limit": limit, "program_id": program_id}

from .proposal_upsert_statements import (
    ACTION_EXPERIENCE_PROPOSAL_UPSERT_SQL,
    action_experience_proposal_values,
    surface_component_proposal_values,
)


ACTION_EXPERIENCE_PROPOSAL_RUN_UPSERT_SQL = """
INSERT INTO action_experience_proposal_runs (
    id,
    program_id,
    campaign_id,
    source_outcome_id,
    source_action_id,
    source_job_id,
    source_run_id,
    status,
    candidate_count,
    feature_builder_version,
    feature_keys,
    graph_counts,
    error,
    produced_by,
    created_at,
    updated_at
)
VALUES (
    %(id)s,
    %(program_id)s,
    %(campaign_id)s,
    %(source_outcome_id)s,
    %(source_action_id)s,
    %(source_job_id)s,
    %(source_run_id)s,
    %(status)s,
    %(candidate_count)s,
    %(feature_builder_version)s,
    %(feature_keys)s,
    %(graph_counts)s,
    %(error)s,
    %(produced_by)s,
    %(now)s,
    %(now)s
)
ON CONFLICT (source_outcome_id) DO UPDATE
SET status = EXCLUDED.status,
    candidate_count = EXCLUDED.candidate_count,
    feature_builder_version = EXCLUDED.feature_builder_version,
    feature_keys = EXCLUDED.feature_keys,
    graph_counts = EXCLUDED.graph_counts,
    error = NULL,
    produced_by = EXCLUDED.produced_by,
    updated_at = EXCLUDED.updated_at
RETURNING id;
""".strip()

def proposal_run_values(
    *,
    proposal_run_id: object,
    source_values: dict[str, object],
    status: str,
    candidate_count: int,
    feature_builder_version: str,
    feature_keys: tuple[str, ...],
    graph_counts: object,
    produced_by: str,
    now: object,
) -> dict[str, object]:
    return {
        "id": proposal_run_id,
        **source_values,
        "status": status,
        "candidate_count": candidate_count,
        "feature_builder_version": feature_builder_version,
        "feature_keys": list(feature_keys),
        "graph_counts": dict(graph_counts),
        "error": None,
        "produced_by": produced_by,
        "now": now,
    }

ACTION_EXPERIENCE_FAILED_PROPOSAL_RUN_UPSERT_SQL = """
INSERT INTO action_experience_proposal_runs (
    id,
    program_id,
    campaign_id,
    source_outcome_id,
    source_action_id,
    source_job_id,
    source_run_id,
    status,
    candidate_count,
    feature_builder_version,
    feature_keys,
    graph_counts,
    error,
    produced_by,
    created_at,
    updated_at
)
VALUES (
    %(id)s,
    %(program_id)s,
    %(campaign_id)s,
    %(source_outcome_id)s,
    %(source_action_id)s,
    %(source_job_id)s,
    %(source_run_id)s,
    'failed',
    0,
    %(feature_builder_version)s,
    %(feature_keys)s,
    %(graph_counts)s,
    %(error)s,
    %(produced_by)s,
    %(now)s,
    %(now)s
)
ON CONFLICT (source_outcome_id) DO UPDATE
SET status = 'failed',
    candidate_count = 0,
    feature_builder_version = EXCLUDED.feature_builder_version,
    feature_keys = EXCLUDED.feature_keys,
    graph_counts = EXCLUDED.graph_counts,
    error = EXCLUDED.error,
    produced_by = EXCLUDED.produced_by,
    updated_at = EXCLUDED.updated_at
RETURNING id;
""".strip()


def failed_proposal_run_values(
    *,
    proposal_run_id: object,
    source_values: dict[str, object],
    feature_builder_version: str,
    error: str,
    produced_by: str,
    now: object,
) -> dict[str, object]:
    return {
        "id": proposal_run_id,
        **source_values,
        "feature_builder_version": feature_builder_version,
        "feature_keys": [],
        "graph_counts": {},
        "error": error[:4000],
        "produced_by": produced_by,
        "now": now,
    }

ACTION_EXPERIENCE_REVIEW_PRIORS_SQL = """
SELECT capability_id,
       profile_id,
       count(*) FILTER (WHERE status = 'accepted') AS accepted_count,
       count(*) FILTER (WHERE status = 'rejected') AS rejected_count,
       count(*) FILTER (WHERE status = 'suppressed') AS suppressed_count,
       coalesce(sum(CASE WHEN status = 'accepted'
                         THEN coalesce(NULLIF(explanation->'review'->>'confidence', '')::double precision, 1.0)
                         ELSE 0.0 END), 0.0) AS accepted_confidence,
       coalesce(sum(CASE WHEN status = 'rejected'
                         THEN coalesce(NULLIF(explanation->'review'->>'confidence', '')::double precision, 1.0)
                         ELSE 0.0 END), 0.0) AS rejected_confidence,
       coalesce(sum(CASE WHEN status = 'suppressed'
                         THEN coalesce(NULLIF(explanation->'review'->>'confidence', '')::double precision, 1.0)
                         ELSE 0.0 END), 0.0) AS suppressed_confidence
FROM action_experience_proposals
WHERE program_id = %(program_id)s
  AND (%(campaign_id)s IS NULL OR campaign_id = %(campaign_id)s)
  AND status IN ('accepted', 'rejected', 'suppressed')
  AND (%(proposal_source)s IS NULL OR explanation->>'source' = %(proposal_source)s)
GROUP BY capability_id, profile_id;
""".strip()

def review_priors_values(
    *,
    program_id: object,
    campaign_id: object | None,
    proposal_source: str | None,
) -> dict[str, object]:
    return {
        "program_id": program_id,
        "campaign_id": campaign_id,
        "proposal_source": proposal_source,
    }

ACTION_EXPERIENCE_PROPOSAL_REVIEW_UPDATE_SQL = """
UPDATE action_experience_proposals
SET status = %(status)s,
    explanation = COALESCE(explanation, '{}'::jsonb) || %(review_payload)s::jsonb,
    updated_at = %(now)s
WHERE id = %(proposal_id)s
  AND status = 'pending'
RETURNING id, capability_id, profile_id, %(previous_status)s AS previous_status, status;
""".strip()

def proposal_review_update_values(
    *,
    proposal_id: object,
    status: str,
    actor: str,
    reason: str | None,
    confidence: float,
    source: str,
    now: object,
) -> dict[str, object]:
    return {
        "proposal_id": proposal_id,
        "status": status,
        "previous_status": "pending",
        "review_payload": {
            "review": {
                "status": status,
                "actor": actor,
                "reason": reason,
                "confidence": confidence,
                "source": source,
                "reviewed_at": now.isoformat(),
            }
        },
        "source": source,
        "now": now,
    }

ACTION_EXPERIENCE_PROPOSAL_ROWS_SQL = """
SELECT capability_id,
       profile_id,
       rank,
       utility_score
FROM action_experience_proposals
WHERE proposal_run_id = %(proposal_run_id)s
ORDER BY rank ASC, utility_score DESC
LIMIT %(top_k)s;
""".strip()

PREVIOUS_ACTION_EXPERIENCE_PROPOSAL_RUN_SQL = """
SELECT previous_run.id AS proposal_run_id
FROM action_experience_proposal_runs previous_run
WHERE previous_run.program_id = %(program_id)s
  AND (%(campaign_id)s IS NULL OR previous_run.campaign_id = %(campaign_id)s)
  AND previous_run.source_outcome_id <> %(source_outcome_id)s
  AND previous_run.status IN ('completed', 'no_candidates')
ORDER BY previous_run.updated_at DESC, previous_run.created_at DESC
LIMIT 1;
""".strip()

UPDATE_ACTION_EXPERIENCE_DECISION_SHIFT_SQL = """
UPDATE action_experience_proposal_runs
SET graph_counts = COALESCE(graph_counts, '{}'::jsonb) || %(decision_graph_counts)s::jsonb,
    updated_at = %(now)s
WHERE id = %(proposal_run_id)s;
""".strip()

def proposal_distribution_values(*, proposal_run_id: object, top_k: int) -> dict[str, object]:
    return {"proposal_run_id": proposal_run_id, "top_k": top_k}


def previous_proposal_run_values(
    *,
    program_id: object,
    campaign_id: object | None,
    source_outcome_id: object,
) -> dict[str, object]:
    return {
        "program_id": program_id,
        "campaign_id": campaign_id,
        "source_outcome_id": source_outcome_id,
    }

def decision_shift_values(*, proposal_run_id: object, payload: dict[str, object], now: object) -> dict[str, object]:
    return {
        "proposal_run_id": proposal_run_id,
        "decision_graph_counts": payload,
        "now": now,
    }

UPDATE_ACTION_EXPERIENCE_PROPOSAL_RUN_CANDIDATE_COUNT_SQL = """
UPDATE action_experience_proposal_runs
SET candidate_count = candidate_count + %(proposal_count)s,
    updated_at = %(now)s
WHERE id = %(proposal_run_id)s;
""".strip()

def proposal_run_candidate_count_values(
    *,
    proposal_run_id: object,
    proposal_count: int,
    now: object,
) -> dict[str, object]:
    return {
        "proposal_count": proposal_count,
        "proposal_run_id": proposal_run_id,
        "now": now,
    }
