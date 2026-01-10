"""Refactored orchestrator - thin event dispatcher using pipeline nodes"""

from typing import Dict, Any
import asyncio
import logging
from dishka import AsyncContainer

from api.config import Settings
from api.infrastructure.events.event_bus import EventBus
from api.infrastructure.events.event_types import EventType
from api.application.pipeline.bootstrap import build_node_registry
from api.application.pipeline.registry import NodeRegistry

logger = logging.getLogger(__name__)


class Orchestrator:
    """
    Thin event dispatcher using NodeRegistry.

    Responsibilities:
    - Subscribe to EventBus
    - Dispatch events to registered nodes
    - Manage background tasks

    NOT responsible for:
    - Business logic (in nodes)
    - Scope filtering (in ScopePolicy)
    - Service execution (in nodes via ctx)
    """

    def __init__(
        self,
        bus: EventBus,
        container: AsyncContainer,
        settings: Settings,
    ):
        self.bus = bus
        self.container = container
        self.settings = settings
        self.registry: NodeRegistry = build_node_registry(bus, container, settings)
        self.tasks: set[asyncio.Task] = set()

    async def start(self):
        """Start orchestrator and subscribe to all events handled by nodes"""
        await self.bus.connect()

        for event_type in self._get_handled_events():
            asyncio.create_task(
                self.bus.subscribe(event_type, self._create_dispatcher(event_type))
            )
            logger.debug(f"Subscribed to event: {event_type}")

        logger.info(
            f"Orchestrator started: {len(self.registry.list_nodes())} nodes, "
            f"{len(self._get_handled_events())} events"
        )

    def _get_handled_events(self) -> list[EventType]:
        """Get all event types that have registered node handlers"""
        return [node.event_in for node in self.registry.list_nodes()]

    def _create_dispatcher(self, event_type: EventType):
        """Create dispatcher function for specific event type"""
        async def dispatcher(event: Dict[str, Any]):
            await self._dispatch_to_node(event_type, event)
        return dispatcher

    async def _dispatch_to_node(self, event_type: EventType, event: Dict[str, Any]):
        """
        Dispatch event to registered node.
        Creates background task to avoid blocking queue processing.
        """
        node = self.registry.get(event_type)
        if not node:
            logger.warning(f"No node registered for event: {event_type}")
            return

        task = asyncio.create_task(self._process_with_node(node, event))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def _process_with_node(self, node, event: Dict[str, Any]):
        """Process event with node and handle errors"""
        try:
            await node.process(event)
        except Exception as exc:
            logger.error(
                f"Node processing failed: node={node.__class__.__name__} "
                f"error={exc}",
                exc_info=True,
            )

    async def stop(self):
        """Stop orchestrator and wait for all tasks to complete"""
        logger.info(f"Stopping orchestrator: {len(self.tasks)} tasks pending")

        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)

        logger.info("Orchestrator stopped")
