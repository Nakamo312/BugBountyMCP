from __future__ import annotations

import json
import uuid
from typing import Any
from urllib.parse import parse_qsl, urlsplit


HTTP_OBSERVATION_ROWS_SQL = """
SELECT
    ho.id::text AS id,
    ho.id::text AS observation_id,
    ho.program_id::text AS program_id,
    ho.endpoint_id::text AS endpoint_id,
    ho.service_id::text AS service_id,
    ho.job_id::text AS job_id,
    ho.run_id::text AS run_id,
    ho.correlation_id::text AS correlation_id,
    ho.raw_artifact_id::text AS raw_artifact_id,
    ho.body_artifact_id::text AS body_artifact_id,
    ho.method,
    ho.url,
    h.host,
    e.path,
    ho.status_code,
    ho.content_type,
    ho.title,
    ho.body_sha256,
    ho.body_size_bytes,
    ho.body_preview AS body_preview_safe,
    ho.source_tool,
    ho.metadata,
    ho.observed_at,
    COALESCE(
        jsonb_object_agg(lower(hh.name), NULL) FILTER (WHERE hh.id IS NOT NULL),
        '{}'::jsonb
    ) AS headers,
    true AS safe_for_llm,
    true AS safe_for_search,
    'research-sanitizer-v1' AS sanitizer_version,
    'redaction-policy-v1' AS redaction_policy_version
FROM http_observations ho
JOIN endpoints e ON e.id = ho.endpoint_id
JOIN hosts h ON h.id = e.host_id
LEFT JOIN http_observation_headers hh ON hh.observation_id = ho.id
WHERE ho.body_preview IS NOT NULL
   OR ho.title IS NOT NULL
   OR ho.status_code IS NOT NULL
GROUP BY ho.id, e.path, h.host
ORDER BY ho.observed_at DESC, ho.id DESC
LIMIT %s
"""


INSERT_PRODUCER_RUN_SQL = """
INSERT INTO research_producer_runs (
    id,
    producer_name,
    producer_version,
    rule_version,
    status,
    stats_json
) VALUES (
    %(id)s::uuid,
    %(producer_name)s,
    %(producer_version)s,
    %(rule_version)s,
    %(status)s,
    %(stats_json)s::jsonb
)
"""


FINISH_PRODUCER_RUN_SQL = """
UPDATE research_producer_runs
SET
    status = %(status)s,
    stats_json = %(stats_json)s::jsonb,
    error = %(error)s,
    finished_at = now()
WHERE id = %(id)s::uuid
"""


UPSERT_HYPOTHESIS_SQL = """
INSERT INTO research_hypotheses (
    id,
    program_id,
    hypothesis_type,
    hypothesis_fingerprint,
    status,
    state_version,
    priority_score,
    confidence,
    severity_guess,
    safety_level,
    score_version,
    inputs_hash,
    source_signal_fingerprints
) VALUES (
    %(id)s::uuid,
    %(program_id)s::uuid,
    %(hypothesis_type)s,
    %(hypothesis_fingerprint)s,
    %(status)s,
    %(state_version)s,
    %(priority_score)s,
    %(confidence)s,
    %(severity_guess)s,
    %(safety_level)s,
    %(score_version)s,
    %(inputs_hash)s,
    %(source_signal_fingerprints)s::jsonb
)
ON CONFLICT (program_id, hypothesis_type, hypothesis_fingerprint)
DO UPDATE SET
    last_seen = now(),
    updated_at = now(),
    priority_score = EXCLUDED.priority_score,
    confidence = EXCLUDED.confidence,
    severity_guess = EXCLUDED.severity_guess,
    safety_level = EXCLUDED.safety_level,
    score_version = EXCLUDED.score_version,
    inputs_hash = EXCLUDED.inputs_hash,
    source_signal_fingerprints = EXCLUDED.source_signal_fingerprints
"""


UPSERT_EVIDENCE_SQL = """
INSERT INTO research_hypothesis_evidence (
    id,
    hypothesis_id,
    ref_type,
    ref_id,
    field_path,
    role,
    claim_type,
    claim,
    evidence_fingerprint,
    safe_excerpt,
    safe_excerpt_truncated,
    safe_excerpt_hash,
    evidence_source,
    normalized_content_hash,
    sanitized_content_hash,
    sanitizer_version,
    redaction_policy_version,
    sensitivity_level,
    redaction_rules_triggered,
    safe_for_search,
    safe_for_embedding,
    safe_for_llm
) VALUES (
    %(id)s::uuid,
    %(hypothesis_id)s::uuid,
    %(ref_type)s,
    %(ref_id)s,
    %(field_path)s,
    %(role)s,
    %(claim_type)s,
    %(claim)s,
    %(evidence_fingerprint)s,
    %(safe_excerpt)s,
    %(safe_excerpt_truncated)s,
    %(safe_excerpt_hash)s,
    %(evidence_source)s,
    %(normalized_content_hash)s,
    %(sanitized_content_hash)s,
    %(sanitizer_version)s,
    %(redaction_policy_version)s,
    %(sensitivity_level)s,
    %(redaction_rules_triggered)s::jsonb,
    %(safe_for_search)s,
    %(safe_for_embedding)s,
    %(safe_for_llm)s
)
ON CONFLICT (hypothesis_id, evidence_fingerprint)
DO UPDATE SET
    safe_excerpt = EXCLUDED.safe_excerpt,
    safe_excerpt_truncated = EXCLUDED.safe_excerpt_truncated,
    safe_excerpt_hash = EXCLUDED.safe_excerpt_hash,
    sanitized_content_hash = EXCLUDED.sanitized_content_hash,
    sanitizer_version = EXCLUDED.sanitizer_version,
    redaction_policy_version = EXCLUDED.redaction_policy_version,
    sensitivity_level = EXCLUDED.sensitivity_level,
    redaction_rules_triggered = EXCLUDED.redaction_rules_triggered,
    safe_for_search = EXCLUDED.safe_for_search,
    safe_for_embedding = EXCLUDED.safe_for_embedding,
    safe_for_llm = EXCLUDED.safe_for_llm
"""


INSERT_SCORE_HISTORY_SQL = """
INSERT INTO research_hypothesis_score_history (
    id,
    hypothesis_id,
    score_version,
    priority_score,
    confidence,
    severity_guess,
    safety_level,
    inputs_hash,
    factors_json
)
SELECT
    %(id)s::uuid,
    %(hypothesis_id)s::uuid,
    %(score_version)s,
    %(priority_score)s,
    %(confidence)s,
    %(severity_guess)s,
    %(safety_level)s,
    %(inputs_hash)s,
    %(factors_json)s::jsonb
WHERE NOT EXISTS (
    SELECT 1
    FROM research_hypothesis_score_history
    WHERE hypothesis_id = %(hypothesis_id)s::uuid
      AND score_version = %(score_version)s
      AND inputs_hash = %(inputs_hash)s
)
"""


INSERT_EVENT_SQL = """
INSERT INTO research_hypothesis_events (
    id,
    hypothesis_id,
    event_type,
    aggregate_version,
    actor,
    reason,
    payload_json
) VALUES (
    %(id)s::uuid,
    %(hypothesis_id)s::uuid,
    %(event_type)s,
    %(aggregate_version)s,
    %(actor)s,
    %(reason)s,
    %(payload_json)s::jsonb
)
ON CONFLICT (hypothesis_id, aggregate_version) DO NOTHING
"""


def fetch_observation_rows(dsn: str, limit: int) -> list[dict[str, Any]]:
    """Fetch HTTP observation candidate rows for safe evidence pack building."""
    _require_dsn(dsn)
    if limit <= 0:
        raise ValueError("limit must be positive")

    with _connect(dsn) as connection:
        connection.set_session(readonly=True, autocommit=True)
        with connection.cursor(cursor_factory=_real_dict_cursor()) as cursor:
            cursor.execute(HTTP_OBSERVATION_ROWS_SQL, (limit,))
            return [_normalize_observation_row(dict(row)) for row in cursor.fetchall()]


def start_producer_run(dsn: str, producer_name: str, producer_version: str, rule_version: str) -> str:
    """Create a research_producer_runs row and return its id."""
    _require_dsn(dsn)
    _require_text(producer_name, "producer_name")
    _require_text(producer_version, "producer_version")
    _require_text(rule_version, "rule_version")

    producer_run_id = str(uuid.uuid4())
    with _connect(dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                INSERT_PRODUCER_RUN_SQL,
                {
                    "id": producer_run_id,
                    "producer_name": producer_name,
                    "producer_version": producer_version,
                    "rule_version": rule_version,
                    "status": "running",
                    "stats_json": _json({}),
                },
            )
        connection.commit()
    return producer_run_id


def upsert_research_rows(dsn: str, rows: Any) -> None:
    """Idempotently upsert research hypotheses, evidence, score history, and events."""
    _require_dsn(dsn)
    if not hasattr(rows, "hypotheses") or not hasattr(rows, "events"):
        raise ValueError("producer_run_id-backed research rows are required")

    with _connect(dsn) as connection:
        with connection.cursor() as cursor:
            for hypothesis in rows.hypotheses:
                params = dict(hypothesis)
                params["source_signal_fingerprints"] = _json(params.get("source_signal_fingerprints") or [])
                cursor.execute(UPSERT_HYPOTHESIS_SQL, params)

            for evidence in rows.evidence:
                params = dict(evidence)
                params["redaction_rules_triggered"] = _json(params.get("redaction_rules_triggered") or [])
                cursor.execute(UPSERT_EVIDENCE_SQL, params)

            for score in rows.score_history:
                params = dict(score)
                params["id"] = str(uuid.uuid4())
                params["factors_json"] = _json(params.get("factors_json") or {})
                cursor.execute(INSERT_SCORE_HISTORY_SQL, params)

            for event in rows.events:
                params = dict(event)
                params["id"] = str(uuid.uuid4())
                params["payload_json"] = _json(params.get("payload_json") or {})
                cursor.execute(INSERT_EVENT_SQL, params)
        connection.commit()


def finish_producer_run(
    dsn: str,
    producer_run_id: str,
    status: str,
    stats: dict[str, Any],
    error: str | None = None,
) -> None:
    """Mark a research_producer_runs row as completed or failed with stats."""
    _require_dsn(dsn)
    _require_text(producer_run_id, "producer_run_id")
    _require_text(status, "status")
    if status not in {"completed", "failed"}:
        raise ValueError("status must be completed or failed")
    if not isinstance(stats, dict):
        raise ValueError("stats must be a dict")
    if error is not None and not isinstance(error, str):
        raise ValueError("error must be a string or None")

    with _connect(dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                FINISH_PRODUCER_RUN_SQL,
                {
                    "id": producer_run_id,
                    "status": status,
                    "stats_json": _json(stats),
                    "error": error,
                },
            )
        connection.commit()


def _normalize_observation_row(row: dict[str, Any]) -> dict[str, Any]:
    row["query_params"] = _query_params_from_url(row.get("url"))
    headers = row.get("headers")
    row["headers"] = headers if isinstance(headers, dict) else {}
    return row


def _query_params_from_url(url: Any) -> list[dict[str, str]]:
    if not isinstance(url, str) or "?" not in url:
        return []
    return [{"name": name, "value": value} for name, value in parse_qsl(urlsplit(url).query, keep_blank_values=True)]


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _connect(dsn: str):
    import psycopg2

    return psycopg2.connect(dsn)


def _real_dict_cursor():
    from psycopg2.extras import RealDictCursor

    return RealDictCursor


def _require_dsn(dsn: str) -> None:
    _require_text(dsn, "dsn")


def _require_text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} is required")
