from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
from uuid import UUID

from ..row_codec import optional_text, optional_uuid, required_row_text, required_row_uuid
from .http_observation_projection import canonical_hostname, required_int, supported_source_tool
from .javascript_reference_keys import canonical_url_without_query


@dataclass(frozen=True)
class JavaScriptReferenceProjection:
    program_id: UUID
    reference_id: UUID
    run_id: UUID
    raw_artifact_id: UUID
    source_tool: str
    source_url: str
    reference_type: str
    hostname: str
    scheme: str
    port: int
    method: str
    normalized_path: str


def javascript_reference_projection_from_row(row: Mapping[str, Any]) -> JavaScriptReferenceProjection | None:
    source_tool = supported_source_tool(row.get("source_tool"))
    if source_tool is None:
        return None

    run_id = optional_uuid(row.get("run_id"))
    raw_artifact_id = optional_uuid(row.get("raw_artifact_id"))
    if run_id is None or raw_artifact_id is None:
        return None

    return JavaScriptReferenceProjection(
        program_id=required_uuid(row, "program_id"),
        reference_id=required_uuid(row, "javascript_reference_id"),
        run_id=run_id,
        raw_artifact_id=raw_artifact_id,
        source_tool=source_tool,
        source_url=canonical_url_without_query(required_text(row, "source_url")),
        reference_type=optional_text(row.get("reference_type")) or "endpoint",
        hostname=canonical_hostname(required_text(row, "hostname")),
        scheme=required_text(row, "scheme").lower(),
        port=required_int(row, "port"),
        method="GET",
        normalized_path=required_text(row, "normalized_path"),
    )


def required_uuid(row: Mapping[str, Any], key: str) -> UUID:
    return required_row_uuid(row, key, context="javascript reference row")


def required_text(row: Mapping[str, Any], key: str) -> str:
    return required_row_text(row, key, context="javascript reference row")
