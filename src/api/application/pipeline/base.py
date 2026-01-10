"""Base abstractions for pipeline architecture"""

from abc import ABC, abstractmethod
from typing import Any, Dict
import logging
import asyncio

from api.infrastructure.events.event_types import EventType
from api.infrastructure.events.event_bus import EventBus
from api.config import Settings
from dishka import AsyncContainer


logger = logging.getLogger(__name__)


class PipelineContext:
    """
    Context for pipeline nodes with access to shared resources.
    Replaces direct dependencies on Orchestrator internals.
    """

    def __init__(
        self,
        bus: EventBus,
        container: AsyncContainer,
        settings: Settings,
        scope_policy: "ScopePolicy",
    ):
        self.bus = bus
        self.container = container
        self.settings = settings
        self.scope = scope_policy
        self._scan_semaphore = asyncio.Semaphore(settings.ORCHESTRATOR_MAX_CONCURRENT)

    async def emit(self, event_type: EventType, payload: Dict[str, Any]):
        """Emit event to the bus"""
        await self.bus.publish(event_type, payload)
        logger.debug(f"Emitted event: {event_type} with payload keys: {payload.keys()}")

    async def acquire_scan_slot(self):
        """Acquire semaphore slot for rate-limited scanning"""
        return self._scan_semaphore

    def get_scan_delay(self) -> int:
        """Get configured scan delay for cascading prevention"""
        return self.settings.ORCHESTRATOR_SCAN_DELAY


class PipelineNode(ABC):
    """
    Base class for pipeline nodes.
    Each node handles ONE event type and emits zero or more events.

    Architecture:
    - Node is stateless and reusable
    - Node does NOT know about EventBus directly (uses ctx.emit)
    - Node does NOT filter scope directly (uses ctx.scope)
    - Node does NOT manage DI (uses ctx.container)
    """

    event_in: EventType
    event_out: list[EventType]

    def __init__(self, ctx: PipelineContext):
        self.ctx = ctx
        self.logger = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    async def process(self, event: Dict[str, Any]) -> None:
        """
        Process incoming event and emit output events via ctx.emit()

        Args:
            event: Event payload dictionary
        """
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(in={self.event_in}, out={self.event_out})"
