"""Amass Node - subdomain enumeration"""

import logging
from typing import Dict, Any, Set
from uuid import UUID

from api.application.pipeline.node import Node
from api.application.pipeline.context import PipelineContext
from api.infrastructure.runners.amass_cli import AmassCliRunner
from api.infrastructure.ingestors.amass_ingestor import AmassResultIngestor
from api.infrastructure.events.event_types import EventType
from api.application.pipeline.scope_policy import ScopePolicy

logger = logging.getLogger(__name__)


class AmassNode(Node):
    """
    Amass subdomain enumeration node.

    Input events: AMASS_SCAN_REQUESTED
    Output events:
      - RAW_DOMAINS_DISCOVERED (all discovered subdomains)
      - IPS_EXPANDED (all discovered IP addresses)
    """

    def __init__(
        self,
        node_id: str,
        event_in: Set[EventType],
        max_parallelism: int = 1,
        scope_policy=ScopePolicy.NONE
    ):
        event_out = {
            EventType.SUBDOMAIN_DISCOVERED,
            EventType.IPS_EXPANDED
        }
        super().__init__(
            node_id=node_id,
            event_in=event_in,
            event_out=event_out,
            max_parallelism=max_parallelism
        )
        self.logger = logging.getLogger(f"node.{node_id}")
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
        Execute Amass enumeration on domain.

        Args:
            event: Event with 'domain', 'active' fields
            ctx: Node execution context
        """
        program_id = UUID(event["program_id"])
        domain = event.get("domain")
        active = event.get("active", False)

        if not domain:
            self.logger.warning("No domain in event")
            return

        self.logger.info(
            f"Starting Amass enum: node={self.node_id} program={program_id} domain={domain} active={active}"
        )

        runner = await ctx.get_service(AmassCliRunner)
        ingestor = await ctx.get_service(AmassResultIngestor)

        try:
            graph_lines = []
            async for process_event in runner.run(domain, active):
                if process_event.type == "stdout" and process_event.payload:
                    graph_lines.append(process_event.payload.strip())

            if graph_lines:
                ingest_result = await ingestor.ingest(program_id, graph_lines)

                if ingest_result.raw_domains:
                    await ctx.emit(
                        event=EventType.RAW_DOMAINS_DISCOVERED.value,
                        targets=ingest_result.raw_domains,
                        program_id=program_id,
                        confidence=0.9
                    )
                    self.logger.debug(
                        f"Emitted RAW_DOMAINS_DISCOVERED: {len(ingest_result.raw_domains)} domains"
                    )

                if ingest_result.ips:
                    await ctx.emit(
                        event=EventType.IPS_EXPANDED.value,
                        targets=ingest_result.ips,
                        program_id=program_id,
                        confidence=0.9
                    )
                    self.logger.debug(
                        f"Emitted IPS_EXPANDED: {len(ingest_result.ips)} IPs"
                    )

            self.logger.info(
                f"Amass enum completed: node={self.node_id} program={program_id} "
                f"domain={domain} lines={len(graph_lines)}"
            )

        except Exception as exc:
            self.logger.error(
                f"Execution failed for event type={event.get('event')}: {exc}",
                exc_info=True
            )
            raise
