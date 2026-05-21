"""Parse raw output artifacts into normalized tool records."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class NormalizedToolRecord(BaseModel):
    """One parser-normalized record extracted from a raw artifact."""

    model_config = ConfigDict(extra="forbid")

    artifact_id: UUID | None = None
    tool: str
    node_id: str
    event_name: str
    ordinal: int
    raw_event_type: str
    record_type: str = "tool_result"
    payload: dict[str, Any]


class RawArtifactParseResult(BaseModel):
    """Parser output for one raw artifact."""

    model_config = ConfigDict(extra="forbid")

    metadata: dict[str, Any] = Field(default_factory=dict)
    records: list[NormalizedToolRecord] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class ProcessEventArtifactParser:
    """Normalize NDJSON artifacts written by FileRawOutputStore."""

    def parse_path(self, path: str | Path) -> RawArtifactParseResult:
        artifact_path = Path(path)
        metadata: dict[str, Any] = {}
        records: list[NormalizedToolRecord] = []
        errors: list[str] = []

        for line_no, line in enumerate(artifact_path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"line {line_no}: invalid JSON: {exc.msg}")
                continue

            item_type = item.get("type")
            if item_type == "metadata":
                payload = item.get("payload")
                if isinstance(payload, dict):
                    metadata = payload
                else:
                    errors.append(f"line {line_no}: metadata payload must be an object")
                continue

            normalized = self._normalize_event(item, metadata, len(records))
            if normalized is not None:
                records.append(normalized)

        return RawArtifactParseResult(metadata=metadata, records=records, errors=errors)

    def _normalize_event(
        self,
        item: dict[str, Any],
        metadata: dict[str, Any],
        ordinal: int,
    ) -> NormalizedToolRecord | None:
        raw_event_type = item.get("type")
        payload = item.get("payload")

        if raw_event_type == "result":
            parsed_payload = self._normalize_payload(payload)
            if parsed_payload is None:
                return None
        elif raw_event_type == "stdout" and isinstance(payload, str):
            parsed_payload = self._parse_stdout_payload(payload)
        else:
            return None

        artifact_id = metadata.get("artifact_id")
        return NormalizedToolRecord(
            artifact_id=UUID(artifact_id) if artifact_id else None,
            tool=str(metadata.get("runner") or metadata.get("tool") or metadata.get("node_id") or "unknown"),
            node_id=str(metadata.get("node_id") or "unknown"),
            event_name=str(metadata.get("event_name") or "unknown"),
            ordinal=ordinal,
            raw_event_type=str(raw_event_type),
            payload=parsed_payload,
        )

    @staticmethod
    def _normalize_payload(value: Any) -> dict[str, Any] | None:
        if isinstance(value, dict):
            return value
        if isinstance(value, str) and value.strip():
            return {"value": value.strip()}
        return None

    @classmethod
    def _parse_stdout_payload(cls, value: str) -> dict[str, Any]:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {"value": value.strip()}
        if isinstance(parsed, dict):
            return parsed
        return {"value": parsed}
