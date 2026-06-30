"""Raw process-event capture for pipeline executions."""
from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any
from uuid import UUID

from api.application.ports.artifacts import (
    RawArtifactMetadataWriter,
    RawOutputCapturePort,
)
from api.application.process_event_contracts import ProcessEvent


class RawArtifactCapture:
    """Capture runner raw output through application ports."""

    def __init__(
        self,
        *,
        node_id: str,
        raw_outputs: RawOutputCapturePort,
        metadata_writer: RawArtifactMetadataWriter,
        mark_run_needs_reconcile: Callable[[str], Awaitable[None]],
    ) -> None:
        self.node_id = node_id
        self.raw_outputs = raw_outputs
        self.metadata_writer = metadata_writer
        self.mark_run_needs_reconcile = mark_run_needs_reconcile

    def capture_stream(
        self,
        stream: AsyncIterator[ProcessEvent],
        *,
        program_id: UUID,
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
    ) -> AsyncIterator[ProcessEvent]:
        return self.raw_outputs.capture_stream(
            stream,
            program_id=program_id,
            node_id=self.node_id,
            event_name=event_name,
            targets=targets,
            job_id=job_id,
            run_id=run_id,
            artifact_id=artifact_id,
            metadata=metadata,
            parser_name=parser_name,
            parser_version=parser_version,
            scope_decision_id=scope_decision_id,
            parent_artifact_id=parent_artifact_id,
            recorder=self.record_raw_artifact,
        )

    async def record_raw_artifact(self, metadata: dict[str, Any]) -> None:
        try:
            await self.metadata_writer.record(metadata)
        except Exception:
            await self.mark_run_needs_reconcile("raw_artifact_metadata_record_failed")
            raise
