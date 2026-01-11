"""Node registry for event routing"""
from typing import Dict, Set, Any
import asyncio
import logging

from api.infrastructure.events.event_bus import EventBus
from api.infrastructure.events.queue_config import QueueConfig
from api.application.pipeline.node import Node
from api.config import Settings

logger = logging.getLogger(__name__)


class NodeRegistry:
    """
    Thin dispatcher that routes events to registered nodes.
    Replaces monolithic Orchestrator with declarative subscription model.

    Subscribes to fixed queues (discovery, enumeration, validation, analysis)
    and routes events to nodes based on event type strings.
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
        self._event_to_nodes: Dict[str, Set[str]] = {}

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

        if hasattr(node, 'set_context_factory'):
            node.set_context_factory(self.bus, self.container, self.settings)

        self._nodes[node.node_id] = node

        for event_type in node.event_in:
            event_str = event_type.value if hasattr(event_type, 'value') else str(event_type)
            if event_str not in self._event_to_nodes:
                self._event_to_nodes[event_str] = set()
            self._event_to_nodes[event_str].add(node.node_id)

        event_in_str = [e.value if hasattr(e, 'value') else str(e) for e in node.event_in]
        event_out_str = [e.value if hasattr(e, 'value') else str(e) for e in node.event_out]

        logger.info(
            f"Registered node: {node.node_id} "
            f"(in={event_in_str}, out={event_out_str})"
        )

    async def start(self):
        """Start EventBus subscriptions for all fixed queues"""
        await self.bus.connect()

        for queue_name in QueueConfig.get_all_queues():
            asyncio.create_task(
                self.bus.subscribe(queue_name, self._dispatch_event)
            )

        logger.info(
            f"NodeRegistry started: {len(self._nodes)} nodes, "
            f"{len(self._event_to_nodes)} event types, "
            f"{len(QueueConfig.get_all_queues())} queues"
        )
        logger.info(f"Registered nodes: {list(self._nodes.keys())}")
        logger.info(f"Event mappings: {dict(self._event_to_nodes)}")

    async def stop(self):
        """Stop all nodes and await their completion"""
        logger.info("Stopping NodeRegistry...")

        stop_tasks = [node.stop() for node in self._nodes.values()]
        await asyncio.gather(*stop_tasks, return_exceptions=True)

        logger.info("NodeRegistry stopped")

    async def _dispatch_event(self, event: Dict[str, Any]):
        """
        Dispatch event to all nodes subscribed to its type.

        Event format:
        {
            "event": "host_discovered",
            "target": "admin.example.com",
            "source": "dnsx",
            "confidence": 0.7,
            "program_id": 42
        }

        Args:
            event: Event dictionary
        """
        event_name = event.get("event")
        if not event_name:
            logger.warning("Event missing 'event' field")
            return

        logger.info(f"Received event: {event_name}, target={event.get('target', 'N/A')}")

        node_ids = self._event_to_nodes.get(event_name, set())
        if not node_ids:
            logger.info(f"No nodes registered for event: {event_name}")
            return

        logger.info(f"Dispatching {event_name} to nodes: {node_ids}")

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
            event_in_str = [e.value if hasattr(e, 'value') else str(e) for e in node.event_in]
            event_out_str = [e.value if hasattr(e, 'value') else str(e) for e in node.event_out]

            nodes.append({
                "id": node_id,
                "event_in": event_in_str,
                "event_out": event_out_str,
                "max_parallelism": node.max_parallelism,
            })

            for out_event in node.event_out:
                out_event_str = out_event.value if hasattr(out_event, 'value') else str(out_event)
                target_nodes = self._event_to_nodes.get(out_event_str, set())
                for target_id in target_nodes:
                    edges.append({
                        "from": node_id,
                        "to": target_id,
                        "event": out_event_str,
                    })

        return {"nodes": nodes, "edges": edges}
