"""Pipeline execution context"""
import logging
from typing import Dict, Any, Optional, Type, TypeVar, List, Tuple
from uuid import UUID
from dishka import AsyncContainer

from api.infrastructure.events.event_bus import EventBus
from api.infrastructure.events.event_types import EventType
from api.config import Settings
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
                    if confidence < self.confidence_threshold:
                        logger.info(
                            f"Dropping event: node={self.node_id} confidence={confidence} "
                            f"threshold={self.confidence_threshold}"
                        )
                        return

        if not targets:
            logger.info(f"No targets to emit after scope filter: node={self.node_id}")
            return

        await self._bus.publish({
            "event": event,
            "targets": targets,
            "source": source or self.node_id,
            "confidence": confidence,
            "program_id": str(program_id),
        })

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
