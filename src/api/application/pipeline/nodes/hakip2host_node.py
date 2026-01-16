"""Hakip2host Node - reverse IP to hostname resolution"""

import logging
from typing import Dict, Any, Set
from uuid import UUID

from api.application.pipeline.node import Node
from api.application.pipeline.context import PipelineContext
from api.infrastructure.runners.hakip2host_cli import Hakip2HostCliRunner
from api.application.services.batch_processor import Hakip2HostBatchProcessor
from api.infrastructure.events.event_types import EventType

logger = logging.getLogger(__name__)


class Hakip2HostNode(Node):
    """
    Hakip2host reverse resolution node.

    Input events: IPS_EXPANDED
    Output events:
      - SUBDOMAIN_DISCOVERED (hostnames from PTR/SSL-SAN/SSL-CN)
    """

    def __init__(
        self,
        node_id: str,
        event_in: Set[EventType],
        max_parallelism: int = 1
    ):
        event_out = {
            EventType.SUBDOMAIN_DISCOVERED
        }
        super().__init__(
            node_id=node_id,
            event_in=event_in,
            event_out=event_out,
            max_parallelism=max_parallelism
        )
        self.logger = logging.getLogger(f"node.{node_id}")

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
            settings=getattr(self, '_settings', None)
        )

    async def execute(self, event: Dict[str, Any], ctx: PipelineContext):
        """
        Execute hakip2host reverse resolution on IPs.

        Args:
            event: Event with 'targets' field containing IPv4 addresses
            ctx: Node execution context
        """
        program_id = UUID(event["program_id"])
        targets = event.get("targets", [])

        if not targets:
            self.logger.warning("No targets in event")
            return

        self.logger.info(
            f"Starting reverse resolution: node={self.node_id} program={program_id} ips={len(targets)}"
        )

        runner = await ctx.get_service(Hakip2HostCliRunner)
        processor = await ctx.get_service(Hakip2HostBatchProcessor)

        batch_count = 0
        total_hostnames = 0
        discovered_hostnames = []

        try:
            async for batch in processor.batch_stream(runner.run(targets)):
                if not batch:
                    continue

                batch_count += 1

                for result in batch:
                    hostname = result.get("hostname")
                    method = result.get("method", "unknown")

                    if not hostname:
                        continue

                    total_hostnames += 1
                    discovered_hostnames.append(hostname)
                    self.logger.debug(
                        f"Resolved: {result.get('ip')} -> {hostname} via {method}"
                    )

            if discovered_hostnames:
                await ctx.emit(
                    event=EventType.SUBDOMAIN_DISCOVERED,
                    targets=discovered_hostnames,
                    program_id=program_id,
                    confidence=0.85
                )
                self.logger.debug(
                    f"Emitted SUBDOMAIN_DISCOVERED: {len(discovered_hostnames)} hostnames"
                )

            self.logger.info(
                f"Reverse resolution completed: node={self.node_id} program={program_id} "
                f"batches={batch_count} hostnames={total_hostnames}"
            )

        except Exception as exc:
            self.logger.error(
                f"Execution failed for event type={event.get('event')}: {exc}",
                exc_info=True
            )
            raise
