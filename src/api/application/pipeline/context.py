"""Pipeline execution context.

PipelineContext is an execution facade kept for node ergonomics. It may bind
events, expose runner context, and delegate to explicit ports/hooks. Do not add
new persistence, storage, scheduling, or outcome side effects here; add a port or
terminal hook and inject it through PipelineContextFactory instead.
"""
from __future__ import annotations
import logging
from collections.abc import AsyncIterator, Mapping
from typing import TYPE_CHECKING, Dict, Any, Optional, Type, TypeVar, List, Tuple
from uuid import UUID, uuid4

from api.application.process_event_contracts import ProcessEvent
from api.config import Settings
from api.application.contracts import EventEnvelope, IngestContext
from api.application.pipeline.scope_policy import ScopePolicy
from api.application.pipeline.invocation import RUNNER_CONTEXT_PAYLOAD_KEY
from api.application.action_outcomes import ActionOutcomeRecorder
from api.application.ports.artifacts import RawArtifactMetadataWriter, RawOutputCapturePort
from api.application.ports.orchestration import PipelineRunStatePort
from api.application.ports.scope import ScopeFilterPort
from api.application.pipeline.raw_artifact_capture import RawArtifactCapture
from api.application.pipeline.run_completion_reporter import RunCompletionReporter

if TYPE_CHECKING:
    from api.infrastructure.events.event_bus import EventBus

logger = logging.getLogger(__name__)

T = TypeVar('T')

LINEAGE_PAYLOAD_KEY = "execution_lineage"

_LINEAGE_FIELD_MAP = {
    "action_id": "root_action_id",
    "capability_id": "root_capability_id",
    "profile_id": "root_profile_id",
    "safety_level": "root_safety_level",
    "policy_decision_id": "policy_decision_id",
    "scope_decision_id": "scope_decision_id",
    "requested_by": "requested_by",
    "execution_budget": "root_execution_budget",
}


class PipelineContext:
    """
    Short-lived execution facade for node execution.

    This class intentionally delegates raw capture, run completion, and scope
    filtering to injected collaborators. New side effects must not be added here.
    """

    execution_facade_only = True

    def __init__(
        self,
        node_id: str,
        bus: Optional[EventBus] = None,
        container: Any | None = None,
        settings: Optional[Settings] = None,
        scope_policy: ScopePolicy = ScopePolicy.NONE,
        confidence_threshold: float = 0.6,
        raw_outputs: RawOutputCapturePort | None = None,
        raw_artifact_metadata: RawArtifactMetadataWriter | None = None,
        run_states: PipelineRunStatePort | None = None,
        action_outcomes: ActionOutcomeRecorder | None = None,
        scope_filter: ScopeFilterPort | None = None,
    ):
        self.node_id = node_id
        self._bus = bus
        self._container = container
        self._settings = settings
        self.scope_policy = scope_policy
        self.confidence_threshold = confidence_threshold
        self.event_id: UUID | None = None
        self.event_name: str | None = None
        self.job_id: UUID | None = None
        self.run_id: UUID | None = None
        self.campaign_id: UUID | None = None
        self.correlation_id: UUID | None = None
        self.expansion_depth: int = 0
        self.execution_lineage: dict[str, Any] = {}
        self.current_runner_context: dict[str, Any] = {}
        self.downstream_parent_artifact_id: UUID | None = None
        self.retry_policy: dict[str, Any] = {
            "max_attempts": 1,
            "backoff_seconds": 0,
            "terminal_outcomes": [],
        }
        self._run_completion_reporter = RunCompletionReporter(
            run_states=run_states,
            outcomes=action_outcomes,
            node_id=node_id,
        )
        self._scope_filter = scope_filter
        self._raw_artifact_capture = (
            RawArtifactCapture(
                node_id=node_id,
                raw_outputs=raw_outputs,
                metadata_writer=raw_artifact_metadata,
                mark_run_needs_reconcile=self._mark_run_needs_reconcile,
            )
            if raw_outputs is not None and raw_artifact_metadata is not None
            else None
        )

    def bind_event(self, event: Dict[str, Any]) -> None:
        self.event_name = event.get("event")
        self.event_id = self._optional_uuid(event.get("event_id"))
        self.job_id = self._optional_uuid(event.get("job_id"))
        self.run_id = self._optional_uuid(event.get("run_id"))
        self.campaign_id = self._optional_uuid(event.get("campaign_id"))
        self.correlation_id = self._optional_uuid(event.get("correlation_id"))
        self.expansion_depth = max(0, int(event.get("expansion_depth", 0) or 0))
        self.execution_lineage = self._extract_execution_lineage(event)
        self.downstream_parent_artifact_id = self._optional_uuid(
            event.get("parent_artifact_id")
            or self._payload_mapping(event).get("parent_artifact_id")
        )
        self._run_completion_reporter.bind_event(
            event_name=self.event_name,
            event_id=self.event_id,
            run_id=self.run_id,
        )

    async def emit(
        self,
        event: str,
        targets: list,
        program_id: UUID,
        source: Optional[str] = None,
        confidence: float = 0.5
    ):
        if not self._bus:
            raise RuntimeError("EventBus not available in context")

        original_count = len(targets)

        if self.scope_policy != ScopePolicy.NONE:
            in_scope, out_scope = await self.filter_by_scope(program_id, targets)

            logger.info(
                f"Scope filter: node={self.node_id} policy={self.scope_policy.value} "
                f"total={original_count} in_scope={len(in_scope)} out_scope={len(out_scope)}"
            )

            if out_scope:
                logger.debug(f"Out-of-scope targets: {out_scope[:5]}...")

            if self.scope_policy in {ScopePolicy.STRICT, ScopePolicy.APPROVAL_REQUIRED}:
                targets = in_scope

            elif self.scope_policy == ScopePolicy.CONFIDENCE:
                if in_scope:
                    confidence = max(confidence, 0.9)
                    targets = in_scope
                else:
                    logger.info(
                        f"Dropping out-of-scope event: node={self.node_id} "
                        f"confidence={confidence} out_scope={len(out_scope)}"
                    )
                    return

        if not targets:
            logger.info(f"No targets to emit after scope filter: node={self.node_id}")
            return

        if self.job_id is None and getattr(self._bus, "requires_bound_job_id_for_recording", False):
            raise RuntimeError("Cannot durably emit pipeline event without bound job_id")

        envelope_kwargs: dict[str, Any] = {
            "event": event,
            "targets": targets,
            "source": source or self.node_id,
            "confidence": confidence,
            "program_id": program_id,
            "causation_id": self.event_id,
            "run_id": uuid4(),
            "campaign_id": self.campaign_id,
            "expansion_depth": self.expansion_depth + 1,
        }
        if self.job_id is not None:
            envelope_kwargs["job_id"] = self.job_id
        if self.correlation_id is not None:
            envelope_kwargs["correlation_id"] = self.correlation_id

        payload = self._downstream_payload()
        if payload:
            envelope_kwargs["payload"] = payload

        await self._bus.publish(EventEnvelope(**envelope_kwargs))

    def set_downstream_parent_artifact(self, artifact_id: UUID | None) -> None:
        """Attach the current raw artifact as parent lineage for emitted events."""
        self.downstream_parent_artifact_id = artifact_id

    def set_current_runner_context(self, context: Any) -> None:
        """Attach current-node execution context to downstream event payloads."""
        if hasattr(context, "downstream_payload"):
            payload = context.downstream_payload()
        elif hasattr(context, "model_dump"):
            payload = context.model_dump(mode="json", exclude_none=True)
        elif isinstance(context, Mapping):
            payload = dict(context)
        else:
            payload = {}
        self.current_runner_context = {
            str(key): self._json_safe(value)
            for key, value in payload.items()
            if value is not None
        }

    def _downstream_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if self.execution_lineage:
            payload[LINEAGE_PAYLOAD_KEY] = dict(self.execution_lineage)
        if self.current_runner_context:
            payload[RUNNER_CONTEXT_PAYLOAD_KEY] = dict(self.current_runner_context)
        if self.downstream_parent_artifact_id is not None:
            payload["parent_artifact_id"] = str(self.downstream_parent_artifact_id)
        return payload

    @classmethod
    def _extract_execution_lineage(cls, event: Mapping[str, Any]) -> dict[str, Any]:
        payload = cls._payload_mapping(event)
        inherited = event.get(LINEAGE_PAYLOAD_KEY) or payload.get(LINEAGE_PAYLOAD_KEY)
        lineage = dict(inherited) if isinstance(inherited, Mapping) else {}

        for source_key, lineage_key in _LINEAGE_FIELD_MAP.items():
            value = event.get(source_key)
            if value is None:
                value = payload.get(source_key)
            if value is not None:
                lineage.setdefault(lineage_key, cls._json_safe(value))

        if event.get("campaign_id") is not None:
            lineage.setdefault("campaign_id", str(event["campaign_id"]))
        if event.get("correlation_id") is not None:
            lineage.setdefault("correlation_id", str(event["correlation_id"]))
        return {key: value for key, value in lineage.items() if value is not None}


    @staticmethod
    def _payload_mapping(event: Mapping[str, Any]) -> Mapping[str, Any]:
        payload = event.get("payload")
        return payload if isinstance(payload, Mapping) else {}

    @staticmethod
    def _json_safe(value: Any) -> Any:
        if isinstance(value, UUID):
            return str(value)
        if isinstance(value, Mapping):
            return {
                str(key): PipelineContext._json_safe(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [PipelineContext._json_safe(item) for item in value]
        return value

    async def get_service(self, service_type: Type[T]) -> T:
        if not self._container:
            raise RuntimeError("DI container not available in context")
        async with self._container() as request_container:
            return await request_container.get(service_type)

    @property
    def settings(self) -> Settings:
        if not self._settings:
            raise RuntimeError("Settings not available in context")
        return self._settings

    def capture_raw_stream(
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
        if self._raw_artifact_capture is None:
            raise RuntimeError("Raw artifact capture not available in context")
        return self._raw_artifact_capture.capture_stream(
            stream,
            program_id=program_id,
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
        )

    def ingest_context(self, raw_artifact_id: UUID | None = None) -> IngestContext:
        return IngestContext(
            job_id=self.job_id,
            run_id=self.run_id,
            correlation_id=self.correlation_id,
            raw_artifact_id=raw_artifact_id,
        )

    async def _mark_run_needs_reconcile(self, reason: str) -> None:
        await self._run_completion_reporter.mark_run_needs_reconcile(reason)

    async def mark_run_started(self) -> bool:
        return await self._run_completion_reporter.mark_run_started()

    async def mark_run_completed(self) -> bool:
        return await self._run_completion_reporter.mark_run_completed(
            retry_policy=self.retry_policy,
        )

    async def mark_run_flushing(self) -> bool:
        return await self._run_completion_reporter.mark_run_flushing()

    async def mark_run_failed(self, error: Exception) -> bool:
        return await self._run_completion_reporter.mark_run_failed(
            error,
            retry_policy=self.retry_policy,
        )

    async def filter_by_scope(self, program_id: UUID, targets: List[str]) -> Tuple[List[str], List[str]]:
        if self._scope_filter is None:
            raise RuntimeError("Scope filter not available in context")
        return await self._scope_filter.filter_by_scope(
            program_id=program_id,
            targets=targets,
            policy=self.scope_policy,
        )

    @staticmethod
    def _optional_uuid(value: Any) -> UUID | None:
        if value in (None, ""):
            return None
        if isinstance(value, UUID):
            return value
        return UUID(str(value))
