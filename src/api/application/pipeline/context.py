"""Pipeline execution context"""
from typing import Dict, Any, Optional, Type, TypeVar, List, Tuple
from uuid import UUID
from dishka import AsyncContainer

from api.infrastructure.events.event_bus import EventBus
from api.infrastructure.events.event_types import EventType
from api.config import Settings

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
    ):
        """
        Initialize pipeline context.

        Args:
            node_id: ID of the node that created this context
            bus: EventBus for emitting events
            container: DI container for service access
            settings: Application settings
        """
        self.node_id = node_id
        self._bus = bus
        self._container = container
        self._settings = settings

    async def emit(self, event_type: EventType, payload: Dict[str, Any]):
        """
        Emit event to EventBus.

        Args:
            event_type: Type of event to publish
            payload: Event payload

        Raises:
            RuntimeError: If EventBus not available in context
        """
        if not self._bus:
            raise RuntimeError("EventBus not available in context")
        await self._bus.publish(event_type, payload)

    async def get_service(self, service_type: Type[T]) -> T:
        """
        Get service from DI container.

        Args:
            service_type: Type of service to retrieve

        Returns:
            Service instance

        Raises:
            RuntimeError: If DI container not available in context
        """
        if not self._container:
            raise RuntimeError("DI container not available in context")
        async with self._container() as request_container:
            return await request_container.get(service_type)

    @property
    def settings(self) -> Settings:
        """
        Get application settings.

        Returns:
            Application settings

        Raises:
            RuntimeError: If settings not available in context
        """
        if not self._settings:
            raise RuntimeError("Settings not available in context")
        return self._settings

    async def filter_by_scope(self, program_id: UUID, targets: List[str]) -> Tuple[List[str], List[str]]:
        """
        Filter targets by program scope rules.

        Args:
            program_id: Program UUID
            targets: List of domains or URLs to filter

        Returns:
            Tuple of (in_scope_targets, out_of_scope_targets)
        """
        from api.infrastructure.unit_of_work.interfaces.program import ProgramUnitOfWork
        from api.application.services.base_service import ScopeCheckMixin

        if not self._container:
            raise RuntimeError("DI container not available in context")

        async with self._container() as request_container:
            program_uow = await request_container.get(ProgramUnitOfWork)
            async with program_uow:
                scope_rules = await program_uow.scope_rules.find_by_program(program_id)
                return ScopeCheckMixin.filter_in_scope(targets, scope_rules)
