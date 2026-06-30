"""Factory wiring explicit PipelineContext dependencies."""
from __future__ import annotations

from typing import Any

from api.application.action_outcomes import ActionOutcomeRecorder
from api.application.ports.artifacts import RawArtifactMetadataWriter, RawOutputCapturePort
from api.application.ports.events import EventBusPort
from api.application.ports.orchestration import PipelineRunStatePort
from api.application.ports.scope import ScopeFilterPort
from api.application.pipeline.context import PipelineContext
from api.application.pipeline.scope_policy import ScopePolicy
from api.config import Settings


class PipelineContextFactory:
    """Build PipelineContext instances from already-wired ports."""

    def __init__(
        self,
        *,
        raw_outputs: RawOutputCapturePort | None,
        raw_artifact_metadata: RawArtifactMetadataWriter | None,
        run_states: PipelineRunStatePort | None,
        action_outcomes: ActionOutcomeRecorder | None,
        scope_filter: ScopeFilterPort | None,
    ) -> None:
        self.raw_outputs = raw_outputs
        self.raw_artifact_metadata = raw_artifact_metadata
        self.run_states = run_states
        self.action_outcomes = action_outcomes
        self.scope_filter = scope_filter

    def create(
        self,
        *,
        node_id: str,
        bus: EventBusPort | None,
        container: Any | None,
        settings: Settings | None,
        scope_policy: ScopePolicy,
        confidence_threshold: float = 0.6,
    ) -> PipelineContext:
        return PipelineContext(
            node_id=node_id,
            bus=bus,
            container=container,
            settings=settings,
            scope_policy=scope_policy,
            confidence_threshold=confidence_threshold,
            raw_outputs=self.raw_outputs,
            raw_artifact_metadata=self.raw_artifact_metadata,
            run_states=self.run_states,
            action_outcomes=self.action_outcomes,
            scope_filter=self.scope_filter,
        )
