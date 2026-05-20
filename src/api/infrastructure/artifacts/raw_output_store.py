"""Filesystem-backed raw tool output artifacts."""
from __future__ import annotations

import json
import hashlib
import logging
import re
from collections.abc import AsyncIterator
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable
from uuid import UUID, uuid4

from api.infrastructure.schemas.models.process_event import ProcessEvent

logger = logging.getLogger(__name__)
_SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9_.-]+")
ArtifactRecorder = Callable[[dict[str, Any]], Awaitable[None]]


def _safe_name(value: str) -> str:
    return _SAFE_NAME_RE.sub("-", value).strip("-") or "unknown"


class FileRawOutputStore:
    """Append-only NDJSON storage for runner output before ingestion."""

    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir)

    def capture_stream(
        self,
        stream: AsyncIterator[ProcessEvent],
        *,
        program_id: UUID,
        node_id: str,
        event_name: str,
        targets: list[str],
        job_id: UUID | None = None,
        run_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
        recorder: ArtifactRecorder | None = None,
    ) -> AsyncIterator[ProcessEvent]:
        artifact_id = uuid4()
        artifact_path = self._artifact_path(
            program_id=program_id,
            node_id=node_id,
            event_name=event_name,
            artifact_id=artifact_id,
        )
        storage_uri = artifact_path.as_posix()
        return self._write_stream(
            stream,
            artifact_path=artifact_path,
            metadata={
                "artifact_id": str(artifact_id),
                "artifact_type": "raw_tool_output",
                "program_id": str(program_id),
                "job_id": str(job_id) if job_id else None,
                "run_id": str(run_id) if run_id else None,
                "node_id": node_id,
                "event_name": event_name,
                "targets": targets,
                "storage_uri": storage_uri,
                "created_at": datetime.now(timezone.utc).isoformat(),
                **(metadata or {}),
            },
            record_metadata={
                "id": artifact_id,
                "program_id": program_id,
                "job_id": job_id,
                "run_id": run_id,
                "node_id": node_id,
                "event_name": event_name,
                "artifact_type": "raw_tool_output",
                "storage_uri": storage_uri,
                "artifact_metadata": {
                    "targets": targets,
                    **(metadata or {}),
                },
            },
            recorder=recorder,
        )

    def _artifact_path(
        self,
        *,
        program_id: UUID,
        node_id: str,
        event_name: str,
        artifact_id: UUID,
    ) -> Path:
        day = datetime.now(timezone.utc).strftime("%Y%m%d")
        return (
            self.base_dir
            / str(program_id)
            / _safe_name(node_id)
            / day
            / f"{_safe_name(event_name)}-{artifact_id}.ndjson"
        )

    async def _write_stream(
        self,
        stream: AsyncIterator[ProcessEvent],
        *,
        artifact_path: Path,
        metadata: dict[str, Any],
        record_metadata: dict[str, Any],
        recorder: ArtifactRecorder | None,
    ) -> AsyncIterator[ProcessEvent]:
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = artifact_path.with_suffix(artifact_path.suffix + ".tmp")
        with temp_path.open("w", encoding="utf-8") as file:
            file.write(json.dumps({"type": "metadata", "payload": metadata}, default=str) + "\n")
            async for event in stream:
                file.write(json.dumps(self._event_to_record(event), default=str) + "\n")
                yield event

        sha256 = self._sha256(temp_path)
        size_bytes = temp_path.stat().st_size
        temp_path.replace(artifact_path)

        if recorder is not None:
            try:
                await recorder(
                    {
                        **record_metadata,
                        "storage_uri": artifact_path.as_posix(),
                        "sha256": sha256,
                        "size_bytes": size_bytes,
                    }
                )
            except Exception:
                logger.exception("Failed to record raw artifact metadata: %s", artifact_path)

    @staticmethod
    def _event_to_record(event: ProcessEvent) -> dict[str, Any]:
        if is_dataclass(event):
            record = asdict(event)
        else:
            record = {
                "type": getattr(event, "type", "unknown"),
                "payload": getattr(event, "payload", None),
            }
        return {
            "type": record.get("type"),
            "payload": record.get("payload"),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
