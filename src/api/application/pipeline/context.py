"""Pipeline execution context"""
import logging
from collections.abc import AsyncIterator
from typing import Dict, Any, Optional, Type, TypeVar, List, Tuple
from uuid import UUID, uuid4
from dishka import AsyncContainer

from api.infrastructure.events.event_bus import EventBus
from api.infrastructure.events.event_types import EventType
from api.infrastructure.schemas.models.process_event import ProcessEvent
from api.infrastructure.artifacts.raw_output_store import FileRawOutputStore
from api.infrastructure.artifacts.raw_artifact_repository import RawArtifactRepository
from api.config import Settings
from api.application.contracts import EventEnvelope, ExecutionStatus, IngestContext, TerminalOutcome
from api.application.pipeline.scope_policy import ScopePolicy

logger = logging.getLogger(__name__)

T = TypeVar('T')


class PipelineContext:
    """
    Short-lived execution context providing emit, DI, and settings access.
    Created per execution, destroyed after completion.
    """

    def __init__(
        self,
        node_id: str,
        bus: Optional[EventBus] = None,
        container: Optional[AsyncContainer] = None,
        settings: Optional[Settings] = None,
        scope_policy: ScopePolicy = ScopePolicy.NONE,
        confidence_threshold: float = 0.6,
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
        self.correlation_id: UUID | None = None
        self.retry_policy: dict[str, Any] = {
            "max_attempts": 1,
            "backoff_seconds": 0,
            "terminal_outcomes": [],
        }

    def bind_event(self, event: Dict[str, Any]) -> None:
        self.event_name = event.get("event")
        self.event_id = self._optional_uuid(event.get("event_id"))
        self.job_id = self._optional_uuid(event.get("job_id"))
        self.run_id = self._optional_uuid(event.get("run_id"))
        self.correlation_id = self._optional_uuid(event.get("correlation_id"))

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

            if self.scope_policy == ScopePolicy.STRICT:
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

        envelope_kwargs: dict[str, Any] = {
            "event": event,
            "targets": targets,
            "source": source or self.node_id,
            "confidence": confidence,
            "program_id": program_id,
            "causation_id": self.event_id,
            "job_id": self.job_id or uuid4(),
            "run_id": uuid4(),
        }
        if self.correlation_id is not None:
            envelope_kwargs["correlation_id"] = self.correlation_id

        await self._bus.publish(EventEnvelope(**envelope_kwargs))

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
    ) -> AsyncIterator[ProcessEvent]:
        store = FileRawOutputStore(self.settings.RAW_OUTPUT_DIR)
        return store.capture_stream(
            stream,
            program_id=program_id,
            node_id=self.node_id,
            event_name=event_name,
            targets=targets,
            job_id=job_id,
            run_id=run_id,
            artifact_id=artifact_id,
            metadata=metadata,
            recorder=self._record_raw_artifact,
        )

    def ingest_context(self, raw_artifact_id: UUID | None = None) -> IngestContext:
        return IngestContext(
            job_id=self.job_id,
            run_id=self.run_id,
            correlation_id=self.correlation_id,
            raw_artifact_id=raw_artifact_id,
        )

    async def _record_raw_artifact(self, metadata: dict[str, Any]) -> None:
        if not self._container:
            raise RuntimeError("DI container not available in context")
        async with self._container() as request_container:
            repository = await request_container.get(RawArtifactRepository)
            try:
                await repository.record(metadata)
            except Exception:
                await self._mark_run_needs_reconcile(
                    "raw_artifact_metadata_record_failed"
                )
                raise

    async def _mark_run_needs_reconcile(self, reason: str) -> None:
        if not self._container or self.run_id is None:
            return
        from api.infrastructure.orchestration.store import OrchestrationStore

        try:
            async with self._container() as request_container:
                store = await request_container.get(OrchestrationStore)
                await store.mark_run_needs_reconcile(
                    run_id=self.run_id,
                    reason=reason,
                )
        except Exception:
            logger.warning("Failed to mark run as needing reconcile", exc_info=True)

    async def mark_run_started(self) -> bool:
        if not self._container or self.run_id is None:
            return True

        from api.infrastructure.orchestration.store import OrchestrationStore

        async with self._container() as request_container:
            store = await request_container.get(OrchestrationStore)
            return await store.mark_run_started(
                run_id=self.run_id,
                node_id=self.node_id,
                event_name=self.event_name,
                trigger_event_id=self.event_id,
            )

    async def mark_run_completed(self) -> bool:
        return await self._mark_run_finished(
            ExecutionStatus.COMPLETED,
            terminal_outcome=TerminalOutcome.COMPLETED,
        )

    async def mark_run_flushing(self) -> bool:
        if not self._container or self.run_id is None:
            return True

        from api.infrastructure.orchestration.store import OrchestrationStore

        async with self._container() as request_container:
            store = await request_container.get(OrchestrationStore)
            return await store.mark_run_flushing(run_id=self.run_id)

    async def mark_run_failed(self, error: Exception) -> bool:
        return await self._mark_run_finished(
            ExecutionStatus.FAILED,
            error=str(error),
            terminal_outcome=TerminalOutcome.TOOL_FAILED,
        )

    async def _mark_run_finished(
        self,
        status: ExecutionStatus,
        error: str | None = None,
        terminal_outcome: TerminalOutcome | None = None,
    ) -> bool:
        if not self._container or self.run_id is None:
            return True

        from api.infrastructure.orchestration.store import OrchestrationStore

        async with self._container() as request_container:
            store = await request_container.get(OrchestrationStore)
            return await store.mark_run_finished(
                run_id=self.run_id,
                status=status,
                error=error,
                terminal_outcome=terminal_outcome,
                retry_policy=self.retry_policy,
            )

    async def filter_by_scope(self, program_id: UUID, targets: List[str]) -> Tuple[List[str], List[str]]:
        from api.infrastructure.unit_of_work.interfaces.program import ProgramUnitOfWork
        from api.application.utils.scope_checker import ScopeChecker

        if not self._container:
            raise RuntimeError("DI container not available in context")

        async with self._container() as request_container:
            program_uow = await request_container.get(ProgramUnitOfWork)
            async with program_uow:
                scope_rules = await program_uow.scope_rules.find_by_program(program_id)

                if not scope_rules:
                    logger.warning(
                        f"No scope rules for program={program_id}, all targets pass through"
                    )

                return ScopeChecker.filter_in_scope(targets, scope_rules)

    @staticmethod
    def _optional_uuid(value: Any) -> UUID | None:
        if value in (None, ""):
            return None
        if isinstance(value, UUID):
            return value
        return UUID(str(value))
