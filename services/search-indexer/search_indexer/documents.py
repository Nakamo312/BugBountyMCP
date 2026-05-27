"""Safe OpenSearch document builders.

These functions intentionally operate on plain dictionaries so the indexer can
stay decoupled from the API domain model and SQLAlchemy mappings.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from typing import Any
from uuid import UUID

MAX_BODY_PREVIEW_CHARS = 65_536
MAX_HEADER_VALUE_CHARS = 8_192
MAX_EVIDENCE_STRING_CHARS = 65_536

SENSITIVE_HEADER_NAMES = {
    "authorization",
    "cookie",
    "proxy-authorization",
    "set-cookie",
    "x-api-key",
    "x-auth-token",
}


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


def safe_header_value(name: str, value: Any) -> str:
    if name.lower() in SENSITIVE_HEADER_NAMES:
        return "[redacted]"
    return truncate_text(value, limit=MAX_HEADER_VALUE_CHARS) or ""


def bounded_json(value: Any, *, string_limit: int = MAX_EVIDENCE_STRING_CHARS) -> Any:
    """Recursively bound strings in JSON-like evidence/metadata payloads."""
    value = stringify(value)
    if isinstance(value, str):
        return truncate_text(value, limit=string_limit)
    if isinstance(value, list):
        return [bounded_json(item, string_limit=string_limit) for item in value]
    if isinstance(value, tuple):
        return [bounded_json(item, string_limit=string_limit) for item in value]
    if isinstance(value, Mapping):
        return {
            str(key): bounded_json(item, string_limit=string_limit)
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


def build_http_observation_document(row: Mapping[str, Any]) -> dict[str, Any]:
    observed_at = stringify(row.get("observed_at"))
    doc = {
        "id": stringify(row.get("id")),
        "program_id": stringify(row.get("program_id")),
        "job_id": stringify(row.get("job_id")),
        "run_id": stringify(row.get("run_id")),
        "correlation_id": stringify(row.get("correlation_id")),
        "endpoint_id": stringify(row.get("endpoint_id")),
        "service_id": stringify(row.get("service_id")),
        "raw_artifact_id": stringify(row.get("raw_artifact_id")),
        "body_artifact_id": stringify(row.get("body_artifact_id")),
        "method": row.get("method"),
        "url": row.get("url"),
        "scheme": row.get("scheme"),
        "host": row.get("host"),
        "port": row.get("port"),
        "path": row.get("path"),
        "status_code": row.get("status_code"),
        "content_type": row.get("content_type"),
        "title": truncate_text(row.get("title"), limit=MAX_EVIDENCE_STRING_CHARS),
        "headers": headers_to_document(row.get("headers")),
        "body_sha256": row.get("body_sha256"),
        "body_size_bytes": row.get("body_size_bytes"),
        "body_preview": truncate_text(row.get("body_preview"), limit=MAX_BODY_PREVIEW_CHARS),
        "source_tool": row.get("source_tool"),
        "metadata": bounded_json(row.get("metadata") or {}),
        "observed_at": observed_at,
        "@timestamp": observed_at,
    }
    return {key: value for key, value in doc.items() if value is not None}


def build_artifact_preview_document(row: Mapping[str, Any]) -> dict[str, Any]:
    created_at = stringify(row.get("created_at"))
    doc = {
        "id": stringify(row.get("id")),
        "program_id": stringify(row.get("program_id")),
        "job_id": stringify(row.get("job_id")),
        "run_id": stringify(row.get("run_id")),
        "node_id": row.get("node_id"),
        "event_name": row.get("event_name"),
        "artifact_type": row.get("artifact_type"),
        "storage_uri": row.get("storage_uri"),
        "sha256": row.get("sha256"),
        "size_bytes": row.get("size_bytes"),
        "metadata": bounded_json(row.get("artifact_metadata") or row.get("metadata") or {}),
        "preview": truncate_text(row.get("preview"), limit=MAX_BODY_PREVIEW_CHARS),
        "created_at": created_at,
        "@timestamp": created_at,
    }
    return {key: value for key, value in doc.items() if value is not None}


def build_finding_document(row: Mapping[str, Any]) -> dict[str, Any]:
    doc = {
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
        "description": truncate_text(row.get("description"), limit=MAX_EVIDENCE_STRING_CHARS),
        "evidence": bounded_json(row.get("evidence") or {}),
        "verified": row.get("verified"),
        "false_positive": row.get("false_positive"),
    }
    return {key: value for key, value in doc.items() if value is not None}


def build_detection_signal_document(row: Mapping[str, Any]) -> dict[str, Any]:
    created_at = stringify(row.get("created_at"))
    doc = {
        "id": stringify(row.get("event_id") or row.get("id")),
        "event_store_id": stringify(row.get("id")),
        "event_id": stringify(row.get("event_id")),
        "event_type": row.get("event_type"),
        "program_id": stringify(row.get("program_id")),
        "job_id": stringify(row.get("job_id")),
        "run_id": stringify(row.get("run_id")),
        "correlation_id": stringify(row.get("correlation_id")),
        "causation_id": stringify(row.get("causation_id")),
        "source": row.get("source"),
        "profile": row.get("profile"),
        "confidence": row.get("confidence"),
        "created_at": created_at,
        "@timestamp": created_at,
    }
    return {key: value for key, value in doc.items() if value is not None}
