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
        return self.parser.parse_path(Path(storage_uri))
