"""Artifact ports consumed by application pipeline code."""
from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Protocol
from uuid import UUID

from api.application.process_event_contracts import ProcessEvent

ArtifactMetadataRecorder = Callable[[dict[str, Any]], Awaitable[None]]


class RawArtifactMetadataWriter(Protocol):
    async def record(self, metadata: dict[str, Any]) -> None:
        ...


class RawOutputCapturePort(Protocol):
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
        recorder: ArtifactMetadataRecorder | None = None,
    ) -> AsyncIterator[ProcessEvent]:
        ...
