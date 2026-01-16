"""Smap Node - port scanning with multi-event emission"""

import logging
from typing import Dict, Any, Set
from uuid import UUID

from api.application.pipeline.node import Node
from api.application.pipeline.context import PipelineContext
from api.infrastructure.runners.smap_cli import SmapCliRunner
from api.application.services.batch_processor import SmapBatchProcessor
from api.infrastructure.events.event_types import EventType

logger = logging.getLogger(__name__)


class SmapNode(Node):
    """
    Smap port scanning node.

    Input events: CIDR_DISCOVERED, SMAP_SCAN_REQUESTED
    Output events:
      - IPS_EXPANDED (IPs discovered)
      - SUBDOMAIN_DISCOVERED (hostnames from PTR)
      - SMAP_RESULTS (full scan results with ports/services/vulns)
    """

    def __init__(
        self,
        node_id: str,
        event_in: Set[EventType],
        max_parallelism: int = 1
    ):
        event_out = {
            EventType.IPS_EXPANDED,
            EventType.SUBDOMAIN_DISCOVERED,
            EventType.SMAP_RESULTS
        }
        super().__init__(
            node_id=node_id,
            event_in=event_in,
            event_out=event_out,
            max_parallelism=max_parallelism
        )
        self.logger = logging.getLogger(f"node.{node_id}")

    async def execute(self, event: Dict[str, Any], ctx: PipelineContext):
        """
        Execute smap scan on CIDRs and emit discovered entities.

        Args:
            event: Event with 'targets' field containing CIDRs
            ctx: Node execution context
        """
        program_id = UUID(event["program_id"])
        targets = event.get("targets", [])

        if not targets:
            self.logger.warning("No targets in event")
            return

        self.logger.info(
            f"Starting scan: node={self.node_id} program={program_id} targets={len(targets)}"
        )

        runner = await ctx.get_service(SmapCliRunner)
        processor = await ctx.get_service(SmapBatchProcessor)

        batch_count = 0
        total_ips = 0
        total_hostnames = 0
        total_ports = 0

        discovered_ips = []
        discovered_hostnames = []
        full_results = []

        try:
            async for batch in processor.batch_stream(runner.run(targets)):
                if not batch:
                    continue

                batch_count += 1

                for result in batch:
                    ip = result.get("ip")
                    hostnames = result.get("hostnames", [])
                    ports = result.get("ports", [])

                    if not ip:
                        continue

                    total_ips += 1
                    discovered_ips.append(ip)

                    if hostnames:
                        total_hostnames += len(hostnames)
                        discovered_hostnames.extend(hostnames)

                    if ports:
                        total_ports += len(ports)

                    full_results.append(result)

            if discovered_ips:
                await ctx.emit(
                    event=EventType.IPS_EXPANDED,
                    targets=discovered_ips,
                    program_id=program_id,
                    confidence=0.95
                )
                self.logger.debug(f"Emitted IPS_EXPANDED: {len(discovered_ips)} IPs")

            if discovered_hostnames:
                await ctx.emit(
                    event=EventType.SUBDOMAIN_DISCOVERED,
                    targets=discovered_hostnames,
                    program_id=program_id,
                    confidence=0.9
                )
                self.logger.debug(f"Emitted SUBDOMAIN_DISCOVERED: {len(discovered_hostnames)} hostnames")

            if full_results:
                await ctx.emit(
                    event=EventType.SMAP_RESULTS,
                    targets=full_results,
                    program_id=program_id,
                    confidence=0.95
                )
                self.logger.debug(f"Emitted SMAP_RESULTS: {len(full_results)} scan results")

            self.logger.info(
                f"Scan completed: node={self.node_id} program={program_id} "
                f"batches={batch_count} ips={total_ips} hostnames={total_hostnames} ports={total_ports}"
            )

        except Exception as exc:
            self.logger.error(
                f"Execution failed for event type={event.get('event')}: {exc}",
                exc_info=True
            )
            raise
