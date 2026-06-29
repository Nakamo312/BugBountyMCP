"""Filesystem-backed raw tool output artifacts."""
from __future__ import annotations

import gzip
import hashlib
import json
import logging
import shutil
from collections.abc import AsyncIterator, Iterator
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable
from uuid import UUID, uuid4

from api.infrastructure.schemas.models.process_event import ProcessEvent
from api.application.research.sanitizer import (
    REDACTION_POLICY_VERSION,
    SANITIZER_VERSION,
    sanitize_text,
)

logger = logging.getLogger(__name__)
ArtifactRecorder = Callable[[dict[str, Any]], Awaitable[None]]
DEFAULT_COMPRESSION_THRESHOLD_BYTES = 1024 * 1024
DEFAULT_PREVIEW_LIMIT_BYTES = 16 * 1024
DEFAULT_RETENTION_CLASS = "program_lifetime"
RETENTION_CLASSES = frozenset(
    {"ephemeral", "short_lived", "program_lifetime", "legal_hold"}
)


class FileRawOutputStore:
    """Append-only NDJSON storage for runner output before ingestion."""

    def __init__(
        self,
        base_dir: str | Path,
        *,
        compression_threshold_bytes: int = DEFAULT_COMPRESSION_THRESHOLD_BYTES,
        preview_limit_bytes: int = DEFAULT_PREVIEW_LIMIT_BYTES,
    ):
        if compression_threshold_bytes < 0:
            raise ValueError("compression_threshold_bytes must be non-negative")
        if preview_limit_bytes < 0:
            raise ValueError("preview_limit_bytes must be non-negative")
        self.base_dir = Path(base_dir)
        self.compression_threshold_bytes = compression_threshold_bytes
        self.preview_limit_bytes = preview_limit_bytes

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
        artifact_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
        parser_name: str = "unknown",
        parser_version: str = "1",
        scope_decision_id: UUID | None = None,
        parent_artifact_id: UUID | None = None,
        retention_class: str = DEFAULT_RETENTION_CLASS,
        recorder: ArtifactRecorder | None = None,
    ) -> AsyncIterator[ProcessEvent]:
        if retention_class not in RETENTION_CLASSES:
            raise ValueError(f"unsupported retention_class: {retention_class}")
        if not parser_name.strip():
            raise ValueError("parser_name must be non-empty")
        if not parser_version.strip():
            raise ValueError("parser_version must be non-empty")
        artifact_id = artifact_id or uuid4()
        artifact_metadata = {
            "artifact_id": str(artifact_id),
            "artifact_type": "raw_tool_output",
            "program_id": str(program_id),
            "job_id": str(job_id) if job_id else None,
            "run_id": str(run_id) if run_id else None,
            "node_id": node_id,
            "event_name": event_name,
            "targets": targets,
            **(metadata or {}),
        }
        return self._write_stream(
            stream,
            record_metadata={
                "id": artifact_id,
                "program_id": program_id,
                "job_id": job_id,
                "run_id": run_id,
                "node_id": node_id,
                "event_name": event_name,
                "artifact_type": "raw_tool_output",
                "artifact_metadata": artifact_metadata,
                "retention_class": retention_class,
                "parser_name": parser_name,
                "parser_version": parser_version,
                "scope_decision_id": scope_decision_id,
                "source_targets": list(targets),
                "parent_artifact_id": parent_artifact_id,
            },
            recorder=recorder,
        )

    def _blob_path(self, sha256: str, *, content_encoding: str) -> Path:
        suffix = ".ndjson.gz" if content_encoding == "gzip" else ".ndjson"
        return (
            self.base_dir
            / "blobs"
            / "sha256"
            / sha256[:2]
            / sha256[2:4]
            / f"{sha256}{suffix}"
        )

    async def _write_stream(
        self,
        stream: AsyncIterator[ProcessEvent],
        *,
        record_metadata: dict[str, Any],
        recorder: ArtifactRecorder | None,
    ) -> AsyncIterator[ProcessEvent]:
        temp_dir = self.base_dir / ".tmp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_path = temp_dir / f"{record_metadata['id']}-{uuid4()}.ndjson.tmp"
        digest = hashlib.sha256()
        preview_bytes = bytearray()

        try:
            with temp_path.open("wb") as file:
                async for event in stream:
                    line = self._encode_record(self._event_to_record(event))
                    file.write(line)
                    digest.update(line)
                    remaining = self.preview_limit_bytes - len(preview_bytes)
                    if remaining > 0:
                        preview_bytes.extend(line[:remaining])

            sha256 = digest.hexdigest()
            size_bytes = temp_path.stat().st_size
            preview = bytes(preview_bytes).decode("utf-8", errors="replace")
            sanitized = sanitize_text(
                preview,
                limit=self.preview_limit_bytes,
            )
            record_metadata = {
                **record_metadata,
                "preview": preview,
                "sanitized_preview": sanitized.safe_excerpt,
                "sanitizer_version": SANITIZER_VERSION,
                "redaction_policy_version": REDACTION_POLICY_VERSION,
                "raw_safe_for_llm": False,
                "sanitized_safe_for_llm": sanitized.safe_for_llm,
            }
            existing_blob = self._existing_blob(sha256)
            if existing_blob is not None:
                artifact_path, content_encoding = existing_blob
                storage_size_bytes = artifact_path.stat().st_size
                temp_path.unlink()
            else:
                content_encoding = (
                    "gzip"
                    if size_bytes >= self.compression_threshold_bytes
                    else "identity"
                )
                stored_temp_path = temp_path
                if content_encoding == "gzip":
                    stored_temp_path = temp_path.with_suffix(".ndjson.gz.tmp")
                    self._compress(temp_path, stored_temp_path)
                    temp_path.unlink()

                storage_size_bytes = stored_temp_path.stat().st_size
                artifact_path = self._blob_path(
                    sha256,
                    content_encoding=content_encoding,
                )
                artifact_path.parent.mkdir(parents=True, exist_ok=True)
                if artifact_path.exists():
                    stored_temp_path.unlink()
                else:
                    stored_temp_path.replace(artifact_path)
        finally:
            if temp_path.exists():
                temp_path.unlink()
            compressed_temp_path = temp_path.with_suffix(".ndjson.gz.tmp")
            if compressed_temp_path.exists():
                compressed_temp_path.unlink()

        if recorder is not None:
            try:
                await recorder(
                    {
                        **record_metadata,
                        "storage_uri": artifact_path.as_posix(),
                        "sha256": sha256,
                        "size_bytes": size_bytes,
                        "storage_size_bytes": storage_size_bytes,
                        "content_encoding": content_encoding,
                    }
                )
            except Exception as exc:
                logger.exception("Failed to record raw artifact metadata: %s", artifact_path)
                self._write_reconcile_marker(
                    artifact_path=artifact_path,
                    artifact_metadata={
                        **record_metadata,
                        "storage_uri": artifact_path.as_posix(),
                        "sha256": sha256,
                        "size_bytes": size_bytes,
                        "storage_size_bytes": storage_size_bytes,
                        "content_encoding": content_encoding,
                    },
                    error=exc,
                )
                raise

        for event in self._read_events(artifact_path):
            yield event

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
        }

    @staticmethod
    def _encode_record(record: dict[str, Any]) -> bytes:
        return (
            json.dumps(
                record,
                default=str,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")

    @staticmethod
    def _read_events(artifact_path: Path) -> Iterator[ProcessEvent]:
        opener = gzip.open if artifact_path.suffix == ".gz" else open
        with opener(artifact_path, "rt", encoding="utf-8") as file:
            for line in file:
                if not line.strip():
                    continue
                record = json.loads(line)
                yield ProcessEvent(
                    type=record.get("type", "failed"),
                    payload=record.get("payload"),
                )

    def _existing_blob(self, sha256: str) -> tuple[Path, str] | None:
        for content_encoding in ("gzip", "identity"):
            path = self._blob_path(
                sha256,
                content_encoding=content_encoding,
            )
            if path.exists():
                return path, content_encoding
        return None

    @staticmethod
    def _compress(source_path: Path, destination_path: Path) -> None:
        with source_path.open("rb") as source:
            with destination_path.open("wb") as destination:
                with gzip.GzipFile(
                    filename="",
                    mode="wb",
                    fileobj=destination,
                    mtime=0,
                ) as compressed:
                    shutil.copyfileobj(source, compressed, length=1024 * 1024)

    @staticmethod
    def _write_reconcile_marker(
        *,
        artifact_path: Path,
        artifact_metadata: dict[str, Any],
        error: Exception,
    ) -> None:
        artifact_id = artifact_metadata.get("id", "unknown")
        marker_path = artifact_path.with_name(
            f"{artifact_path.stem}-{artifact_id}.ndjson.reconcile.json"
        )
        marker = {
            "type": "raw_artifact_metadata_record_failed",
            "artifact": artifact_metadata,
            "error": {
                "type": type(error).__name__,
                "message": str(error),
            },
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            marker_path.write_text(
                json.dumps(marker, default=str, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        except Exception:
            logger.exception("Failed to write raw artifact reconcile marker: %s", marker_path)
