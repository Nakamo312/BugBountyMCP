from __future__ import annotations

from dataclasses import dataclass
from ipaddress import ip_address
from typing import Any, Mapping
from uuid import UUID

from ..row_codec import (
    optional_int,
    optional_text,
    optional_uuid,
    required_row_text,
    required_row_uuid,
)


@dataclass(frozen=True)
class HttpObservationProjection:
    program_id: UUID
    observation_id: UUID
    run_id: UUID
    raw_artifact_id: UUID
    source_tool: str
    hostname: str
    ip_address: str
    scheme: str
    port: int
    method: str
    normalized_path: str
    status_code: int | None
    content_type: str | None
    url: str | None


def http_observation_projection_from_row(row: Mapping[str, Any]) -> HttpObservationProjection | None:
    source_tool = supported_source_tool(row.get("source_tool"))
    if source_tool is None:
        return None

    run_id = optional_uuid(row.get("run_id"))
    raw_artifact_id = optional_uuid(row.get("raw_artifact_id"))
    if run_id is None or raw_artifact_id is None:
        return None

    return HttpObservationProjection(
        program_id=required_uuid(row, "program_id"),
        observation_id=required_uuid(row, "observation_id"),
        run_id=run_id,
        raw_artifact_id=raw_artifact_id,
        source_tool=source_tool,
        hostname=canonical_hostname(required_text(row, "hostname")),
        ip_address=canonical_ip_address(required_text(row, "ip_address")),
        scheme=required_text(row, "scheme").lower(),
        port=required_int(row, "port"),
        method=required_text(row, "method").upper(),
        normalized_path=required_text(row, "normalized_path"),
        status_code=optional_int(row.get("status_code")),
        content_type=optional_text(row.get("content_type")),
        url=optional_text(row.get("url")),
    )


def required_uuid(row: Mapping[str, Any], key: str) -> UUID:
    return required_row_uuid(row, key, context="http observation row")


def required_text(row: Mapping[str, Any], key: str) -> str:
    return required_row_text(row, key, context="http observation row")


def required_int(row: Mapping[str, Any], key: str) -> int:
    if row.get(key) is None:
        raise ValueError(f"http observation row requires {key}")
    return int(row[key])


def supported_source_tool(value: Any) -> str | None:
    text = optional_text(value)
    if text is None:
        return None
    return text.lower()


def canonical_hostname(value: str) -> str:
    hostname = value.strip().lower().rstrip(".")
    if not hostname:
        raise ValueError("http observation row requires non-empty hostname")
    return hostname


def canonical_ip_address(value: str) -> str:
    text = value.strip()
    try:
        return str(ip_address(text))
    except ValueError:
        return text
