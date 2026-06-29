"""Safe OpenSearch document builders.

These functions intentionally operate on plain dictionaries so the indexer can
stay decoupled from the API domain model and SQLAlchemy mappings.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
import re
from typing import Any
from uuid import UUID

MAX_BODY_PREVIEW_CHARS = 65_536
MAX_HEADER_VALUE_CHARS = 8_192
MAX_EVIDENCE_STRING_CHARS = 65_536
SCHEMA_VERSION = "1"
SANITIZER_VERSION = "1"

SENSITIVE_HEADER_NAMES = {
    "authorization",
    "cookie",
    "proxy-authorization",
    "set-cookie",
    "x-api-key",
    "x-auth-token",
}
SENSITIVE_KEY_NAMES = SENSITIVE_HEADER_NAMES | {
    "access_token",
    "api_key",
    "apikey",
    "password",
    "passwd",
    "pwd",
    "refresh_token",
    "secret",
    "token",
}
SECRET_PAIR_RE = re.compile(
    r"(?i)\b("
    r"password|passwd|pwd|token|access_token|refresh_token|api[_-]?key|apikey|secret"
    r")=([^&\s]+)"
)


def stringify(value: Any) -> Any:
    """Convert non-JSON-native scalar values into stable strings."""
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def truncate_text(value: Any, *, limit: int) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text[:limit]


def sanitize_text(value: Any, *, limit: int = MAX_EVIDENCE_STRING_CHARS) -> str | None:
    text = truncate_text(value, limit=limit)
    if text is None:
        return None
    return SECRET_PAIR_RE.sub(lambda match: f"{match.group(1)}=[redacted]", text)


def safe_header_value(name: str, value: Any) -> str:
    if name.lower() in SENSITIVE_HEADER_NAMES:
        return "[redacted]"
    return sanitize_text(value, limit=MAX_HEADER_VALUE_CHARS) or ""


def bounded_json(value: Any, *, string_limit: int = MAX_EVIDENCE_STRING_CHARS) -> Any:
    """Recursively bound strings in JSON-like evidence/metadata payloads."""
    value = stringify(value)
    if isinstance(value, str):
        return sanitize_text(value, limit=string_limit)
    if isinstance(value, list):
        return [bounded_json(item, string_limit=string_limit) for item in value]
    if isinstance(value, tuple):
        return [bounded_json(item, string_limit=string_limit) for item in value]
    if isinstance(value, Mapping):
        return {
            str(key): (
                "[redacted]"
                if str(key).strip().lower() in SENSITIVE_KEY_NAMES
                else bounded_json(item, string_limit=string_limit)
            )
            for key, item in value.items()
        }
    return value


def headers_to_document(headers: Any) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for header in headers or []:
        if isinstance(header, Mapping):
            raw_name = header.get("name")
            raw_value = header.get("value")
        else:
            raw_name = getattr(header, "name", None)
            raw_value = getattr(header, "value", None)

        name = str(raw_name or "").strip().lower()
        if not name:
            continue
        result.setdefault(name, []).append(safe_header_value(name, raw_value))
    return result


def technology_names(value: Any) -> list[str]:
    names: set[str] = set()
    if isinstance(value, Mapping):
        names.update(
            str(key).strip().lower()
            for key, enabled in value.items()
            if enabled and str(key).strip()
        )
    elif isinstance(value, (list, tuple, set)):
        names.update(str(item).strip().lower() for item in value if str(item).strip())
    elif isinstance(value, str) and value.strip():
        names.add(value.strip().lower())
    return sorted(names)


def build_http_observation_document(row: Mapping[str, Any]) -> dict[str, Any]:
    observed_at = stringify(row.get("observed_at"))
    doc = {
        "schema_version": SCHEMA_VERSION,
        "sanitizer_version": SANITIZER_VERSION,
        "id": stringify(row.get("id")),
        "program_id": stringify(row.get("program_id")),
        "job_id": stringify(row.get("job_id")),
        "run_id": stringify(row.get("run_id")),
        "correlation_id": stringify(row.get("correlation_id")),
        "endpoint_id": stringify(row.get("endpoint_id")),
        "service_id": stringify(row.get("service_id")),
        "raw_artifact_id": stringify(row.get("raw_artifact_id")),
        "artifact_id": stringify(row.get("raw_artifact_id")),
        "tool_run_id": stringify(row.get("run_id")),
        "body_artifact_id": stringify(row.get("body_artifact_id")),
        "method": row.get("method"),
        "url": row.get("url"),
        "scheme": row.get("scheme"),
        "host": row.get("host"),
        "port": row.get("port"),
        "path": row.get("path"),
        "status_code": row.get("status_code"),
        "content_type": row.get("content_type"),
        "title": sanitize_text(row.get("title"), limit=MAX_EVIDENCE_STRING_CHARS),
        "headers": headers_to_document(row.get("headers")),
        "body_sha256": row.get("body_sha256"),
        "body_size_bytes": row.get("body_size_bytes"),
        "source_tool": row.get("source_tool"),
        "metadata": bounded_json(row.get("metadata") or {}),
        "observed_at": observed_at,
        "@timestamp": observed_at,
    }
    return {key: value for key, value in doc.items() if value is not None}


def build_endpoint_document(row: Mapping[str, Any]) -> dict[str, Any]:
    doc = {
        "schema_version": SCHEMA_VERSION,
        "sanitizer_version": SANITIZER_VERSION,
        "id": stringify(row.get("id")),
        "program_id": stringify(row.get("program_id")),
        "host_id": stringify(row.get("host_id")),
        "service_id": stringify(row.get("service_id")),
        "host": truncate_text(row.get("host"), limit=1_024),
        "scheme": row.get("scheme"),
        "port": row.get("port"),
        "path": truncate_text(row.get("path"), limit=2_048),
        "normalized_path": truncate_text(
            row.get("normalized_path"),
            limit=2_048,
        ),
        "methods": [
            str(method).upper()
            for method in (row.get("methods") or [])
            if str(method).strip()
        ][:16],
        "status_code": row.get("status_code"),
        "technology_names": technology_names(row.get("technologies")),
    }
    return {key: value for key, value in doc.items() if value is not None}


def build_technology_document(row: Mapping[str, Any]) -> dict[str, Any]:
    doc = {
        "schema_version": SCHEMA_VERSION,
        "sanitizer_version": SANITIZER_VERSION,
        "id": stringify(row.get("service_id") or row.get("id")),
        "program_id": stringify(row.get("program_id")),
        "service_id": stringify(row.get("service_id") or row.get("id")),
        "address": row.get("address"),
        "scheme": row.get("scheme"),
        "port": row.get("port"),
        "technology_names": technology_names(row.get("technologies")),
    }
    return {key: value for key, value in doc.items() if value is not None}


def build_artifact_preview_document(row: Mapping[str, Any]) -> dict[str, Any]:
    created_at = stringify(row.get("created_at"))
    safe_preview = (
        truncate_text(
            row.get("sanitized_preview"),
            limit=MAX_BODY_PREVIEW_CHARS,
        )
        if row.get("sanitized_safe_for_llm") is True
        else None
    )
    doc = {
        "schema_version": SCHEMA_VERSION,
        "sanitizer_version": row.get("sanitizer_version") or SANITIZER_VERSION,
        "id": stringify(row.get("id")),
        "artifact_id": stringify(row.get("id")),
        "program_id": stringify(row.get("program_id")),
        "job_id": stringify(row.get("job_id")),
        "run_id": stringify(row.get("run_id")),
        "tool_run_id": stringify(row.get("run_id")),
        "node_id": row.get("node_id"),
        "event_name": row.get("event_name"),
        "artifact_type": row.get("artifact_type"),
        "sha256": row.get("sha256"),
        "size_bytes": row.get("size_bytes"),
        "metadata": bounded_json(row.get("artifact_metadata") or row.get("metadata") or {}),
        "preview": safe_preview,
        "redaction_policy_version": row.get("redaction_policy_version"),
        "created_at": created_at,
        "@timestamp": created_at,
    }
    return {key: value for key, value in doc.items() if value is not None}


def build_finding_document(row: Mapping[str, Any]) -> dict[str, Any]:
    doc = {
        "schema_version": SCHEMA_VERSION,
        "sanitizer_version": SANITIZER_VERSION,
        "id": stringify(row.get("id")),
        "program_id": stringify(row.get("program_id")),
        "vuln_type_id": stringify(row.get("vuln_type_id")),
        "vuln_code": row.get("vuln_code"),
        "severity": row.get("severity"),
        "category": row.get("category"),
        "host_id": stringify(row.get("host_id")),
        "endpoint_id": stringify(row.get("endpoint_id")),
        "parameter_id": stringify(row.get("parameter_id")),
        "payload_id": stringify(row.get("payload_id")),
        "execution_id": stringify(row.get("execution_id")),
        "description": sanitize_text(row.get("description"), limit=MAX_EVIDENCE_STRING_CHARS),
        "evidence": bounded_json(row.get("evidence") or {}),
        "verified": row.get("verified"),
        "false_positive": row.get("false_positive"),
    }
    return {key: value for key, value in doc.items() if value is not None}


def _evidence_items(row: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    items = row.get("evidence") or []
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, Mapping)]


def _unique_strings(values: Any, *, limit: int = 100) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
        if len(result) >= limit:
            break
    return result


def _safe_evidence_text(evidence: list[Mapping[str, Any]]) -> list[str]:
    snippets: list[str] = []
    for item in evidence:
        if item.get("safe_for_search") is not True:
            continue
        for key in ("claim", "safe_excerpt"):
            text = sanitize_text(item.get(key), limit=MAX_EVIDENCE_STRING_CHARS)
            if text:
                snippets.append(text)
    return _unique_strings(snippets, limit=50)


def build_hypothesis_document(row: Mapping[str, Any]) -> dict[str, Any]:
    first_seen = stringify(row.get("first_seen"))
    last_seen = stringify(row.get("last_seen"))
    updated_at = stringify(row.get("updated_at"))
    evidence = _evidence_items(row)
    doc = {
        "schema_version": SCHEMA_VERSION,
        "sanitizer_version": SANITIZER_VERSION,
        "id": stringify(row.get("id")),
        "hypothesis_id": stringify(row.get("id")),
        "program_id": stringify(row.get("program_id")),
        "hypothesis_type": row.get("hypothesis_type"),
        "hypothesis_fingerprint": row.get("hypothesis_fingerprint"),
        "status": row.get("status"),
        "state_version": row.get("state_version"),
        "priority_score": row.get("priority_score"),
        "confidence": row.get("confidence"),
        "severity_guess": row.get("severity_guess"),
        "safety_level": row.get("safety_level"),
        "score_version": row.get("score_version"),
        "inputs_hash": row.get("inputs_hash"),
        "source_signal_fingerprints": _unique_strings(row.get("source_signal_fingerprints")),
        "duplicate_of_hypothesis_id": stringify(row.get("duplicate_of_hypothesis_id")),
        "evidence_count": row.get("evidence_count"),
        "evidence_ref_types": _unique_strings(item.get("ref_type") for item in evidence),
        "evidence_roles": _unique_strings(item.get("role") for item in evidence),
        "evidence_claim_types": _unique_strings(item.get("claim_type") for item in evidence),
        "evidence_ref_ids": _unique_strings(item.get("ref_id") for item in evidence),
        "safe_evidence_text": _safe_evidence_text(evidence),
        "first_seen": first_seen,
        "last_seen": last_seen,
        "updated_at": updated_at,
        "@timestamp": updated_at or last_seen or first_seen,
    }
    return {key: value for key, value in doc.items() if value not in (None, [], {})}

def build_detection_signal_document(row: Mapping[str, Any]) -> dict[str, Any]:
    created_at = stringify(row.get("created_at"))
    doc = {
        "schema_version": SCHEMA_VERSION,
        "sanitizer_version": SANITIZER_VERSION,
        "id": stringify(row.get("event_id") or row.get("id")),
        "event_store_id": stringify(row.get("id")),
        "event_id": stringify(row.get("event_id")),
        "event_type": row.get("event_type"),
        "program_id": stringify(row.get("program_id")),
        "job_id": stringify(row.get("job_id")),
        "run_id": stringify(row.get("run_id")),
        "tool_run_id": stringify(row.get("run_id")),
        "correlation_id": stringify(row.get("correlation_id")),
        "causation_id": stringify(row.get("causation_id")),
        "source": row.get("source"),
        "profile": row.get("profile"),
        "confidence": row.get("confidence"),
        "created_at": created_at,
        "@timestamp": created_at,
    }
    return {key: value for key, value in doc.items() if value is not None}

def build_surface_component_document(row: Mapping[str, Any]) -> dict[str, Any]:
    created_at = stringify(row.get("created_at") or row.get("analysis_created_at"))
    doc = {
        "schema_version": SCHEMA_VERSION,
        "sanitizer_version": SANITIZER_VERSION,
        "id": stringify(row.get("id") or f"{row.get('analysis_run_id')}:{row.get('component_id')}"),
        "analysis_run_id": stringify(row.get("analysis_run_id")),
        "program_id": stringify(row.get("program_id")),
        "snapshot_id": stringify(row.get("snapshot_id")),
        "previous_snapshot_id": stringify(row.get("previous_snapshot_id")),
        "algorithm": row.get("algorithm"),
        "algorithm_version": row.get("algorithm_version"),
        "report_fingerprint": row.get("report_fingerprint"),
        "component_id": row.get("component_id"),
        "node_count": row.get("node_count"),
        "changed_node_count": row.get("changed_node_count"),
        "structural_pressure_score": row.get("structural_pressure_score"),
        "drift_score": row.get("drift_score"),
        "bridge_pressure_score": row.get("bridge_pressure_score"),
        "outlier_score": row.get("outlier_score"),
        "coverage_score": row.get("coverage_score"),
        "exploration_priority_score": row.get("exploration_priority_score"),
        "action_candidate_count": row.get("action_candidate_count"),
        "metrics": bounded_json(row.get("metrics_json") or {}),
        "action_candidates": bounded_json(row.get("action_candidates_json") or [], string_limit=8_192),
        "created_at": created_at,
        "@timestamp": created_at,
    }
    return {key: value for key, value in doc.items() if value not in (None, [], {})}


def build_surface_delta_document(row: Mapping[str, Any]) -> dict[str, Any]:
    created_at = stringify(row.get("created_at"))
    doc = {
        "schema_version": SCHEMA_VERSION,
        "sanitizer_version": SANITIZER_VERSION,
        "id": stringify(row.get("id")),
        "program_id": stringify(row.get("program_id")),
        "from_snapshot_id": stringify(row.get("from_snapshot_id")),
        "to_snapshot_id": stringify(row.get("to_snapshot_id")),
        "delta_type": row.get("delta_type"),
        "subject_type": row.get("subject_type"),
        "subject_fingerprint": row.get("subject_fingerprint"),
        "novelty_score": row.get("novelty_score"),
        "details": bounded_json(row.get("details_json") or {}),
        "created_at": created_at,
        "@timestamp": created_at,
    }
    return {key: value for key, value in doc.items() if value not in (None, [], {})}
