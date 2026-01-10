"""Node registry for event-to-node dispatching"""

from typing import Dict, Optional
import logging

from api.infrastructure.events.event_types import EventType
from .base import PipelineNode


logger = logging.getLogger(__name__)


class NodeRegistry:
    """
    Registry mapping EventType to PipelineNode.

    Architecture:
    - One EventType -> One Node (1:1 mapping)
    - If fan-out needed, Node emits multiple events
    - Registry is immutable after bootstrap
    """

    def __init__(self):
        self._nodes: Dict[EventType, PipelineNode] = {}

    def register(self, node: PipelineNode) -> None:
        """
        Register a pipeline node for its input event type.

        Args:
            node: PipelineNode instance to register

        Raises:
            ValueError: If event_in already registered
        """
        if node.event_in in self._nodes:
            existing = self._nodes[node.event_in]
            raise ValueError(
                f"Event {node.event_in} already registered to {existing.__class__.__name__}, "
                f"cannot register {node.__class__.__name__}"
            )

        self._nodes[node.event_in] = node
        logger.info(f"Registered node: {node}")

    def get(self, event_type: EventType) -> Optional[PipelineNode]:
        """
        Get node for event type.

        Args:
            event_type: EventType to look up

        Returns:
            PipelineNode if registered, None otherwise
        """
        return self._nodes.get(event_type)

    def has_handler(self, event_type: EventType) -> bool:
        """Check if event type has a registered handler"""
        return event_type in self._nodes

    def list_nodes(self) -> list[PipelineNode]:
        """Get all registered nodes"""
        return list(self._nodes.values())

    def get_event_graph(self) -> Dict[EventType, list[EventType]]:
        """
        Build event graph showing which events trigger which.

        Returns:
            Dict mapping input event to list of output events
        """
        graph = {}
        for event_type, node in self._nodes.items():
            graph[event_type] = node.event_out
        return graph

    def __repr__(self) -> str:
        return f"NodeRegistry(nodes={len(self._nodes)})"
