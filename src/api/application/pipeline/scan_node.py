"""Generic scan node for CLI tools"""
from typing import Dict, Any, Set, Optional, Callable, List, Type
from uuid import UUID
import logging

from api.application.pipeline.node import Node
from api.application.pipeline.context import PipelineContext
from api.infrastructure.events.event_types import EventType

logger = logging.getLogger(__name__)


class ScanNode(Node):
    """
    Generic node for CLI scan tools.
    Gets dependencies from DI container on each execution.

    Event Flow:
    1. Receive event from EventBus
    2. Extract targets via target_extractor
    3. Get runner/processor/ingestor from DI (REQUEST scope)
    4. Run: runner → batch processor (streaming)
    5. For each batch:
       - Ingest batch (if ingestor provided)
       - Extract new entities from IngestResult
       - Emit events for new entities
    """

    def __init__(
        self,
        node_id: str,
        event_in: Set[EventType],
        event_out: Dict[EventType, str],
        runner_type: Type,
        processor_type: Type,
        ingestor_type: Optional[Type] = None,
        target_extractor: Optional[Callable[[Dict[str, Any]], List[str]]] = None,
        max_parallelism: int = 1,
        execution_delay: int = 0,
    ):
        """
        Initialize generic scan node.

        Args:
            node_id: Unique node identifier
            event_in: Set of event types this node accepts
            event_out: Map of event_type → result_key for emitting
            runner_type: Runner class (will be resolved from DI)
            processor_type: Processor class (will be resolved from DI)
            ingestor_type: Optional ingestor class (will be resolved from DI)
            target_extractor: Function to extract targets from event
            max_parallelism: Maximum concurrent executions
            execution_delay: Delay in seconds before executing (default: 0)
        """
        super().__init__(
            node_id=node_id,
            event_in=event_in,
            event_out=set(event_out.keys()),
            max_parallelism=max_parallelism,
            execution_delay=execution_delay
        )
        self.event_out_map = event_out
        self.runner_type = runner_type
        self.processor_type = processor_type
        self.ingestor_type = ingestor_type
        self.target_extractor = target_extractor or self._default_target_extractor

    async def execute(self, event: Dict[str, Any], ctx: PipelineContext):
        """
        Execute scan: extract targets → get dependencies from DI → run → batch → ingest → emit.

        Args:
            event: Incoming event data
            ctx: Pipeline context for emitting downstream events
        """
        program_id = UUID(event["program_id"])
        targets = self.target_extractor(event)

        if not targets:
            self.logger.warning(f"No targets in event: {event.get('_event_type')}")
            return

        self.logger.info(
            f"Starting scan: node={self.node_id} program={program_id} targets={len(targets)}"
        )

        runner = await ctx.get_service(self.runner_type)
        processor = await ctx.get_service(self.processor_type)
        ingestor = await ctx.get_service(self.ingestor_type) if self.ingestor_type else None

        batch_count = 0

        try:
            async for batch in processor.batch_stream(runner.run(targets)):
                if not batch:
                    continue

                batch_count += 1

                if ingestor:
                    ingest_result = await ingestor.ingest(program_id, batch)

                    for event_type, result_key in self.event_out_map.items():
                        data = getattr(ingest_result, result_key, [])
                        if data:
                            event_name = event_type.value if hasattr(event_type, 'value') else str(event_type)
                            for item in data:
                                await ctx.emit(
                                    event_name=event_name,
                                    target=item,
                                    program_id=program_id,
                                    confidence=0.7
                                )
                            self.logger.debug(
                                f"Emitted {event_name}: {len(data)} items"
                            )
                else:
                    for event_type, result_key in self.event_out_map.items():
                        if batch:
                            event_name = event_type.value if hasattr(event_type, 'value') else str(event_type)
                            for item in batch:
                                await ctx.emit(
                                    event_name=event_name,
                                    target=item,
                                    program_id=program_id,
                                    confidence=0.5
                                )
                            self.logger.debug(
                                f"Emitted {event_name}: {len(batch)} items"
                            )

            self.logger.info(
                f"Scan completed: node={self.node_id} program={program_id} batches={batch_count}"
            )

        except Exception as exc:
            self.logger.error(
                f"Scan failed: node={self.node_id} program={program_id} error={exc}",
                exc_info=True
            )
            raise

    def set_context_factory(self, bus, container, settings):
        """
        Set dependencies for context creation.
        Called by NodeRegistry after node creation.

        Args:
            bus: EventBus instance
            container: DI container
            settings: Application settings
        """
        self._bus = bus
        self._container = container
        self._settings = settings

    async def _create_context(self) -> PipelineContext:
        """
        Create context with EventBus/DI/Settings injected.

        Returns:
            Pipeline context with all dependencies
        """
        return PipelineContext(
            node_id=self.node_id,
            bus=getattr(self, '_bus', None),
            container=getattr(self, '_container', None),
            settings=getattr(self, '_settings', None)
        )

    @staticmethod
    def _default_target_extractor(event: Dict[str, Any]) -> List[str]:
        """
        Default target extractor for various event types.

        Args:
            event: Event payload

        Returns:
            List of targets (URLs, hosts, IPs, etc.)
        """
        return (
            event.get("subdomains") or
            event.get("urls") or
            event.get("hosts") or
            event.get("ips") or
            event.get("targets") or
            []
        )
