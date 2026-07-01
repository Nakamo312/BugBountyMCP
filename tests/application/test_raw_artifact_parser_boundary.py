from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from api.application.raw_artifact_parsing import RawArtifactParseResult
from api.application.services.raw_artifact_parser import RawArtifactParserService


class RecordingParser:
    def __init__(self) -> None:
        self.path: Path | None = None
        self.metadata: dict[str, Any] | None = None

    def parse_path(
        self,
        path: str | Path,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> RawArtifactParseResult:
        self.path = Path(path)
        self.metadata = metadata
        return RawArtifactParseResult(metadata=dict(metadata or {}))


def test_raw_artifact_parser_service_depends_on_parser_port_only(tmp_path: Path) -> None:
    parser = RecordingParser()
    artifact_id = uuid4()
    program_id = uuid4()
    storage_path = tmp_path / "artifact.ndjson"
    service = RawArtifactParserService(parser)

    parsed = service.parse_metadata_row(
        {
            "id": artifact_id,
            "program_id": program_id,
            "job_id": None,
            "run_id": None,
            "node_id": "probe",
            "event_name": "probe.completed",
            "artifact_type": "process_event_stream",
            "artifact_metadata": {"runner": "ProbeRunner"},
            "storage_uri": str(storage_path),
        }
    )

    assert parser.path == storage_path
    assert parser.metadata == {
        "artifact_id": str(artifact_id),
        "artifact_type": "process_event_stream",
        "program_id": str(program_id),
        "job_id": None,
        "run_id": None,
        "node_id": "probe",
        "event_name": "probe.completed",
        "runner": "ProbeRunner",
    }
    assert parsed.metadata["runner"] == "ProbeRunner"


def test_raw_artifact_parser_service_requires_explicit_parser() -> None:
    try:
        RawArtifactParserService()  # type: ignore[call-arg]
    except TypeError:
        return
    raise AssertionError("RawArtifactParserService must not construct infrastructure parser")
