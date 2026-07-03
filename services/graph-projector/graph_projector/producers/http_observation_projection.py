from __future__ import annotations

from dataclasses import dataclass
from ipaddress import ip_address
import json
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
class InputParameterProjection:
    location: str
    name: str
    param_type: str
    reflected: bool
    is_array: bool


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
    body_sha256: str | None
    body_size_bytes: int | None
    body_artifact_id: UUID | None
    input_parameters: tuple[InputParameterProjection, ...]
    response_header_names: tuple[str, ...]


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
        body_sha256=_optional_sha256(row.get("body_sha256")),
        body_size_bytes=optional_int(row.get("body_size_bytes")),
        body_artifact_id=optional_uuid(row.get("body_artifact_id")),
        input_parameters=_input_parameters(row.get("input_parameters")),
        response_header_names=_response_header_names(row.get("response_header_names")),
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


def _optional_sha256(value: Any) -> str | None:
    text = optional_text(value)
    if text is None:
        return None
    lowered = text.lower()
    return lowered if len(lowered) == 64 and all(ch in "0123456789abcdef" for ch in lowered) else None


def _input_parameters(value: Any) -> tuple[InputParameterProjection, ...]:
    records = _records(value)
    params: list[InputParameterProjection] = []
    seen: set[tuple[str, str]] = set()
    for record in records:
        location = _safe_location(record.get("location"))
        name = _safe_name(record.get("name"))
        if location is None or name is None:
            continue
        key = (location, name)
        if key in seen:
            continue
        seen.add(key)
        params.append(
            InputParameterProjection(
                location=location,
                name=name,
                param_type=_safe_param_type(record.get("param_type")),
                reflected=_safe_bool(record.get("reflected")),
                is_array=_safe_bool(record.get("is_array")),
            )
        )
    return tuple(sorted(params, key=lambda item: (item.location, item.name)))


def _response_header_names(value: Any) -> tuple[str, ...]:
    names: set[str] = set()
    if isinstance(value, (list, tuple, set)):
        values = value
    elif value is None:
        values = ()
    else:
        try:
            parsed = json.loads(str(value))
        except Exception:
            parsed = ()
        values = parsed if isinstance(parsed, list) else ()
    for item in values:
        name = _safe_name(item)
        if name is not None:
            names.add(name.lower())
    return tuple(sorted(names))


def _records(value: Any) -> tuple[Mapping[str, Any], ...]:
    if value is None:
        return ()
    parsed: Any = value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return ()
    if not isinstance(parsed, list):
        return ()
    return tuple(item for item in parsed if isinstance(item, Mapping))


def _safe_location(value: Any) -> str | None:
    text = optional_text(value)
    if text is None:
        return None
    location = text.lower()
    return location if location in {"query", "path", "body", "header", "cookie", "graphql", "form"} else None


def _safe_param_type(value: Any) -> str:
    text = optional_text(value)
    if text is None:
        return "string"
    param_type = text.lower()
    return param_type if param_type in {"string", "integer", "boolean", "array", "object", "file"} else "string"


def _safe_name(value: Any) -> str | None:
    text = optional_text(value)
    if text is None:
        return None
    safe = text.strip().strip("\x00")
    if not safe or len(safe) > 255:
        return None
    return safe


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    text = optional_text(value)
    if text is None:
        return False
    return text.lower() in {"1", "true", "t", "yes", "y"}
