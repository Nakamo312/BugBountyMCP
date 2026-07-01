"""Application boundary for raw artifact parsing."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol
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


class RawArtifactPathParser(Protocol):
    """Parse one raw artifact file into normalized tool records."""

    def parse_path(
        self,
        path: str | Path,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> RawArtifactParseResult:
        raise NotImplementedError
