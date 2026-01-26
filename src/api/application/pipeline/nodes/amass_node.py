"""Amass Node - subdomain enumeration"""

import asyncio
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
    Amass subdomain enumeration node with infrastructure discovery.

    Input events: AMASS_SCAN_REQUESTED
    Output events:
      - SUBDOMAIN_DISCOVERED (DNS-resolved subdomains)
      - IPS_EXPANDED (discovered IP addresses)
      - CIDR_DISCOVERED (discovered network blocks)
      - ASN_DISCOVERED (discovered autonomous systems)
    """

    def __init__(
        self,
        node_id: str,
        event_in: Set[EventType],
        max_parallelism: int = 1,
        max_concurrent_scans: int = 5,
        scope_policy=ScopePolicy.NONE
    ):
        event_out = {
            EventType.SUBDOMAIN_DISCOVERED,
            EventType.IPS_EXPANDED,
            EventType.ASN_DISCOVERED,
            EventType.CIDR_DISCOVERED
        }
        super().__init__(
            node_id=node_id,
            event_in=event_in,
            event_out=event_out,
            max_parallelism=max_parallelism
        )
        self.logger = logging.getLogger(f"node.{node_id}")
        self.scope_policy = scope_policy
        self._scan_semaphore = asyncio.Semaphore(max_concurrent_scans)

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
        Execute Amass enumeration on multiple domains.

        Args:
            event: Event with 'targets' and 'active' fields
            ctx: Node execution context
        """
        program_id = UUID(event["program_id"])
        targets = event.get("targets", [])
        active = event.get("active", False)

        if not targets:
            self.logger.warning("No targets in event")
            return

        self.logger.info(
            f"Starting Amass enum: node={self.node_id} program={program_id} "
            f"targets={len(targets)} active={active}"
        )

        runner = await ctx.get_service(AmassCliRunner)
        ingestor = await ctx.get_service(AmassResultIngestor)

        async def enumerate_single_domain(domain: str) -> tuple[int, int]:
            """Enumerate a single domain and return (domains_found, ips_found)"""
            if not isinstance(domain, str):
                self.logger.warning(f"Skipping non-string target: {domain}")
                return 0, 0

            async with self._scan_semaphore:
                self.logger.info(f"Enumerating domain: {domain} (active={active})")

                graph_lines = []
                async for process_event in runner.run(domain, active):
                    if process_event.type == "stdout" and process_event.payload:
                        graph_lines.append(process_event.payload.strip())

                if graph_lines:
                    ingest_result = await ingestor.ingest(program_id, graph_lines)

                    if ingest_result.raw_domains:
                        await ctx.emit(
                            event=EventType.SUBDOMAIN_DISCOVERED.value,
                            targets=ingest_result.raw_domains,
                            program_id=program_id,
                            confidence=0.9
                        )
                        self.logger.debug(
                            f"Emitted SUBDOMAIN_DISCOVERED for {domain}: "
                            f"{len(ingest_result.raw_domains)} domains"
                        )

                    if ingest_result.ips:
                        await ctx.emit(
                            event=EventType.IPS_EXPANDED.value,
                            targets=ingest_result.ips,
                            program_id=program_id,
                            confidence=0.9
                        )
                        self.logger.debug(
                            f"Emitted IPS_EXPANDED for {domain}: "
                            f"{len(ingest_result.ips)} IPs"
                        )

                    if ingest_result.cidrs:
                        await ctx.emit(
                            event=EventType.CIDR_DISCOVERED.value,
                            targets=ingest_result.cidrs,
                            program_id=program_id,
                            confidence=0.9
                        )
                        self.logger.debug(
                            f"Emitted CIDR_DISCOVERED for {domain}: "
                            f"{len(ingest_result.cidrs)} CIDRs"
                        )

                    if ingest_result.asns:
                        await ctx.emit(
                            event=EventType.ASN_DISCOVERED.value,
                            targets=ingest_result.asns,
                            program_id=program_id,
                            confidence=0.9
                        )
                        self.logger.debug(
                            f"Emitted ASN_DISCOVERED for {domain}: "
                            f"{len(ingest_result.asns)} ASNs"
                        )

                    return len(ingest_result.raw_domains or []), len(ingest_result.ips or [])
                return 0, 0

        try:
            results = await asyncio.gather(
                *[enumerate_single_domain(domain) for domain in targets],
                return_exceptions=True
            )

            total_domains = 0
            total_ips = 0
            failed = 0

            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    self.logger.error(f"Failed to enumerate {targets[i]}: {result}")
                    failed += 1
                elif isinstance(result, tuple):
                    domains_found, ips_found = result
                    total_domains += domains_found
                    total_ips += ips_found

            self.logger.info(
                f"Amass enum completed: node={self.node_id} program={program_id} "
                f"domains={len(targets)} total_domains_found={total_domains} "
                f"total_ips_found={total_ips} failed={failed}"
            )

        except Exception as exc:
            self.logger.error(
                f"Execution failed for event type={event.get('event')}: {exc}",
                exc_info=True
            )
            raise