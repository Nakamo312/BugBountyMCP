"""Factory for creating nodes from configuration"""
from typing import Set, Dict, Optional, Callable, List, Any, Type

from api.application.pipeline.scan_node import ScanNode
from api.application.pipeline.extractors import default_target_extractor
from api.infrastructure.events.event_types import EventType


class NodeFactory:
    """Factory for creating nodes from configuration without boilerplate"""

    @staticmethod
    def create_scan_node(
        node_id: str,
        event_in: Set[EventType],
        event_out: Dict[EventType, str],
        runner_type: Type,
        processor_type: Type,
        ingestor_type: Optional[Type] = None,
        target_extractor: Optional[Callable[[Dict[str, Any]], List[str]]] = None,
        max_parallelism: int = 1,
        execution_delay: int = 0
    ) -> ScanNode:
        """
        Create generic scan node from configuration.

        Args:
            node_id: Unique node identifier
            event_in: Set of event types this node accepts
            event_out: Map of event_type → result_key for emitting
                      e.g., {EventType.HOST_DISCOVERED: "new_hosts"}
            runner_type: Runner class (will be resolved from DI)
            processor_type: Processor class (will be resolved from DI)
            ingestor_type: Optional ingestor class (will be resolved from DI)
            target_extractor: Optional function to extract targets from event
            max_parallelism: Maximum concurrent executions
            execution_delay: Delay in seconds before executing (default: 0)

        Returns:
            Configured ScanNode instance

        Example:
            >>> from api.infrastructure.runners.httpx_cli import HTTPXCliRunner
            >>> from api.application.services.batch_processor import HTTPXBatchProcessor
            >>> from api.infrastructure.ingestors.httpx_ingestor import HTTPXResultIngestor
            >>>
            >>> httpx_node = NodeFactory.create_scan_node(
            ...     node_id="httpx",
            ...     event_in={EventType.SUBDOMAIN_DISCOVERED},
            ...     event_out={
            ...         EventType.HOST_DISCOVERED: "new_hosts",
            ...         EventType.JS_FILES_DISCOVERED: "js_files"
            ...     },
            ...     runner_type=HTTPXCliRunner,
            ...     processor_type=HTTPXBatchProcessor,
            ...     ingestor_type=HTTPXResultIngestor,
            ...     max_parallelism=2
            ... )
        """
        return ScanNode(
            node_id=node_id,
            event_in=event_in,
            event_out=event_out,
            runner_type=runner_type,
            processor_type=processor_type,
            ingestor_type=ingestor_type,
            target_extractor=target_extractor or default_target_extractor,
            max_parallelism=max_parallelism,
            execution_delay=execution_delay
        )
