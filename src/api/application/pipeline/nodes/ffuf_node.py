"""FFUF Node - directory/file fuzzing"""

import asyncio
import logging
from typing import Dict, Any, Set
from uuid import UUID

from api.application.pipeline.node import Node
from api.application.pipeline.context import PipelineContext
from api.infrastructure.runners.ffuf_cli import FFUFCliRunner
from api.infrastructure.ingestors.ffuf_ingestor import FFUFResultIngestor
from api.infrastructure.events.event_types import EventType
from api.application.pipeline.scope_policy import ScopePolicy

logger = logging.getLogger(__name__)


class FFUFNode(Node):
    """
    FFUF fuzzing node.

    Input events: HOST_DISCOVERED, FFUF_SCAN_REQUESTED
    Output events: None (results ingested to DB)
    """

    def __init__(
        self,
        node_id: str,
        event_in: Set[EventType],
        max_parallelism: int = 1,
        max_concurrent_scans: int = 5,
        scope_policy=ScopePolicy.NONE
    ):
        event_out = set()
        super().__init__(
            node_id=node_id,
            event_in=event_in,
            event_out=event_out,
            max_parallelism=max_parallelism
        )
        self.logger = logging.getLogger(f"node.{node_id}")
        self._scan_semaphore = asyncio.Semaphore(max_concurrent_scans)
        self.scope_policy = scope_policy

    def set_context_factory(self, bus, container, settings):
        """
        Set dependencies for context creation.
        Called by NodeRegistry after node creation.
        """
        self._bus = bus
        self._container = container
        self._settings = settings

    async def _create_context(self) -> PipelineContext:
        """Create context with EventBus/DI/Settings injected."""
        return PipelineContext(
            node_id=self.node_id,
            bus=getattr(self, '_bus', None),
            container=getattr(self, '_container', None),
            settings=getattr(self, '_settings', None),
            scope_policy=self.scope_policy
        )

    async def execute(self, event: Dict[str, Any], ctx: PipelineContext):
        """
        Execute FFUF fuzzing on URLs.

        Args:
            event: Event with 'targets' field containing URLs
            ctx: Node execution context
        """
        program_id = UUID(event["program_id"])
        targets = event.get("targets", [])

        if not targets:
            self.logger.warning("No targets in event")
            return

        self.logger.info(
            f"Starting fuzzing: node={self.node_id} program={program_id} targets={len(targets)}"
        )

        runner = await ctx.get_service(FFUFCliRunner)
        ingestor = await ctx.get_service(FFUFResultIngestor)

        async def fuzz_single_target(target_url: str) -> int:
            """Fuzz a single target and return result count"""
            if not isinstance(target_url, str):
                self.logger.warning(f"Skipping non-string target: {target_url}")
                return 0

            async with self._scan_semaphore:
                self.logger.info(f"Fuzzing target: {target_url}")

                results = []
                async for event in runner.run(target_url):
                    if event.type == "result" and event.payload:
                        results.append(event.payload)

                if results:
                    await ingestor.ingest(program_id, results)
                    self.logger.info(f"Ingested {len(results)} results for {target_url}")
                    return len(results)
                return 0

        try:
            result_counts = await asyncio.gather(
                *[fuzz_single_target(url) for url in targets],
                return_exceptions=True
            )

            total_results = sum(r for r in result_counts if isinstance(r, int))
            failed = sum(1 for r in result_counts if isinstance(r, Exception))

            self.logger.info(
                f"Fuzzing completed: node={self.node_id} program={program_id} "
                f"urls={len(targets)} total_results={total_results} failed={failed}"
            )

        except Exception as exc:
            self.logger.error(
                f"Execution failed for event type={event.get('event')}: {exc}",
                exc_info=True
            )
            raise
