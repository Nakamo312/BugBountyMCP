"""Node registry for event routing"""
from typing import Dict, Set, Any
import asyncio
import logging

from api.infrastructure.events.event_bus import EventBus
from api.infrastructure.events.event_types import EventType
from api.application.pipeline.node import Node
from api.config import Settings

logger = logging.getLogger(__name__)


class NodeRegistry:
    """
    Thin dispatcher that routes events to registered nodes.
    Replaces monolithic Orchestrator with declarative subscription model.
    """

    def __init__(self, bus: EventBus, settings: Settings, container=None):
        """
        Initialize node registry.

        Args:
            bus: EventBus for pub/sub
            settings: Application settings
            container: Optional DI container for node context
        """
        self.bus = bus
        self.settings = settings
        self.container = container
        self._nodes: Dict[str, Node] = {}
        self._event_to_nodes: Dict[EventType, Set[str]] = {}

    def register(self, node: Node):
        """
        Register node and subscribe to its input events.

        Args:
            node: Node instance to register

        Raises:
            ValueError: If node already registered
        """
        if node.node_id in self._nodes:
            raise ValueError(f"Node already registered: {node.node_id}")

        # Inject context dependencies if node supports it (ScanNode)
        if hasattr(node, 'set_context_factory'):
            node.set_context_factory(self.bus, self.container, self.settings)

        self._nodes[node.node_id] = node

        for event_type in node.event_in:
            if event_type not in self._event_to_nodes:
                self._event_to_nodes[event_type] = set()
            self._event_to_nodes[event_type].add(node.node_id)

        logger.info(
            f"Registered node: {node.node_id} "
            f"(in={[e.value for e in node.event_in]}, "
            f"out={[e.value for e in node.event_out]})"
        )

    async def start(self):
        """Start EventBus subscriptions for all registered event types"""
        await self.bus.connect()

        for event_type in self._event_to_nodes.keys():
            asyncio.create_task(
                self.bus.subscribe(event_type.value, self._dispatch_event)
            )

        logger.info(
            f"NodeRegistry started: {len(self._nodes)} nodes, "
            f"{len(self._event_to_nodes)} event types"
        )

    async def stop(self):
        """Stop all nodes and await their completion"""
        logger.info("Stopping NodeRegistry...")

        stop_tasks = [node.stop() for node in self._nodes.values()]
        await asyncio.gather(*stop_tasks, return_exceptions=True)

        logger.info("NodeRegistry stopped")

    async def _dispatch_event(self, event: Dict[str, Any]):
        """
        Dispatch event to all nodes subscribed to its type.

        Args:
            event: Event payload
        """
        event_type_str = event.get("_event_type")
        if not event_type_str:
            logger.warning("Event missing _event_type field")
            return

        try:
            event_type = EventType(event_type_str)
        except ValueError:
            logger.warning(f"Unknown event type: {event_type_str}")
            return

        node_ids = self._event_to_nodes.get(event_type, set())
        if not node_ids:
            logger.debug(f"No nodes registered for event: {event_type_str}")
            return

        for node_id in node_ids:
            node = self._nodes[node_id]
            try:
                await node.handle_event(event)
            except Exception as exc:
                logger.error(
                    f"Failed to dispatch event to node {node_id}: {exc}",
                    exc_info=True
                )

    def get_graph(self) -> Dict[str, Any]:
        """
        Get pipeline graph structure for visualization.

        Returns:
            Graph representation with nodes and edges
        """
        nodes = []
        edges = []

        for node_id, node in self._nodes.items():
            nodes.append({
                "id": node_id,
                "event_in": [e.value for e in node.event_in],
                "event_out": [e.value for e in node.event_out],
                "max_parallelism": node.max_parallelism,
            })

            for out_event in node.event_out:
                target_nodes = self._event_to_nodes.get(out_event, set())
                for target_id in target_nodes:
                    edges.append({
                        "from": node_id,
                        "to": target_id,
                        "event": out_event.value,
                    })

        return {"nodes": nodes, "edges": edges}
