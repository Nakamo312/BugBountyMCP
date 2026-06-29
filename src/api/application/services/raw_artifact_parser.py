"""Application service for parsing stored raw artifacts."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from api.infrastructure.parsers.raw_artifact_parser import (
    ProcessEventArtifactParser,
    RawArtifactParseResult,
)


class RawArtifactParserService:
    """Parse raw artifact rows through the configured parser implementation."""

    def __init__(self, parser: ProcessEventArtifactParser | None = None):
        self.parser = parser or ProcessEventArtifactParser()

    def parse_metadata_row(self, row: dict[str, Any]) -> RawArtifactParseResult:
        storage_uri = row.get("storage_uri")
        if not storage_uri:
            raise ValueError("raw artifact row missing storage_uri")
        metadata = {
            "artifact_id": str(row["id"]) if row.get("id") else None,
            "artifact_type": row.get("artifact_type"),
            "program_id": str(row["program_id"]) if row.get("program_id") else None,
            "job_id": str(row["job_id"]) if row.get("job_id") else None,
            "run_id": str(row["run_id"]) if row.get("run_id") else None,
            "node_id": row.get("node_id"),
            "event_name": row.get("event_name"),
            **(row.get("artifact_metadata") or {}),
        }
        return self.parser.parse_path(Path(storage_uri), metadata=metadata)
