"""Amass Node - subdomain enumeration"""

import asyncio
import logging
from typing import Dict, Any, Set, Type
from uuid import UUID, uuid4

from api.application.pipeline.node import Node
from api.application.pipeline.context import PipelineContext
from api.infrastructure.events.event_types import EventType
from api.application.pipeline.scope_policy import ScopePolicy
from api.application.pipeline.ingestion import ingest_with_optional_context
from api.application.contracts import ExecutionMode

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
        runner_key: Type[Any],
        parser_key: Type[Any],
        processor_key: Type[Any],
        ingestor_key: Type[Any],
        event_out: Set[EventType] | None = None,
        max_parallelism: int = 1,
        max_concurrent_scans: int = 5,
        execution_mode: ExecutionMode = ExecutionMode.INLINE,
        max_targets_per_run: int | None = None,
        retry_policy: dict | None = None,
        scope_policy=ScopePolicy.NONE
    ):
        event_out = event_out or {
            EventType.SUBDOMAIN_DISCOVERED,
            EventType.IPS_EXPANDED,
            EventType.ASN_DISCOVERED,
            EventType.CIDR_DISCOVERED
        }
        super().__init__(
            node_id=node_id,
            event_in=event_in,
            event_out=event_out,
            max_parallelism=max_parallelism,
            execution_mode=execution_mode,
            max_targets_per_run=max_targets_per_run,
            retry_policy=retry_policy,
        )
        self.logger = logging.getLogger(f"node.{node_id}")
        self.runner_key = runner_key
        self.parser_key = parser_key
        self.processor_key = processor_key
        self.ingestor_key = ingestor_key
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
        job_id = UUID(event["job_id"]) if event.get("job_id") else None
        run_id = UUID(event["run_id"]) if event.get("run_id") else None
        targets = event.get("targets", [])
        active = event.get("active", False)

        if not targets:
            self.logger.warning("No targets in event")
            return

        self.logger.info(
            f"Starting Amass enum: node={self.node_id} program={program_id} "
            f"targets={len(targets)} active={active}"
        )

        runner = await ctx.get_service(self.runner_key)
        processor = await ctx.get_service(self.processor_key)
        ingestor = await ctx.get_service(self.ingestor_key)
        parser = self.parser_key()

        async def enumerate_single_domain(domain: str) -> tuple[int, int]:
            """Enumerate a single domain and return (domains_found, ips_found)"""
            if not isinstance(domain, str):
                self.logger.warning(f"Skipping non-string target: {domain}")
                return 0, 0

            async with self._scan_semaphore:
                self.logger.info(f"Enumerating domain: {domain} (active={active})")

                stream = runner.run_raw(domain, active)
                raw_artifact_id = uuid4()
                if isinstance(ctx, PipelineContext):
                    stream = ctx.capture_raw_stream(
                        stream,
                        program_id=program_id,
                        event_name=event.get("event", self.node_id),
                        targets=[domain],
                        job_id=job_id,
                        run_id=run_id,
                        artifact_id=raw_artifact_id,
                        metadata={"runner": self.runner_key.__name__, "active": active},
                    )
                stream = parser.parse_stream(stream)
                ingest_context = ctx.ingest_context(raw_artifact_id) if isinstance(ctx, PipelineContext) else None

                raw_domains: set[str] = set()
                ips: set[str] = set()
                cidrs: set[str] = set()
                asns: set[str] = set()

                async for batch in processor.batch_stream(stream):
                    if not batch:
                        continue
                    ingest_result = await ingest_with_optional_context(
                        ingestor,
                        program_id,
                        batch,
                        ingest_context,
                    )
                    raw_domains.update(ingest_result.raw_domains or [])
                    ips.update(ingest_result.ips or [])
                    cidrs.update(ingest_result.cidrs or [])
                    asns.update(ingest_result.asns or [])

                if raw_domains or ips or cidrs or asns:

                    if raw_domains:
                        await ctx.emit(
                            event=EventType.SUBDOMAIN_DISCOVERED.value,
                            targets=sorted(raw_domains),
                            program_id=program_id,
                            confidence=0.9
                        )
                        self.logger.debug(
                            f"Emitted SUBDOMAIN_DISCOVERED for {domain}: "
                            f"{len(raw_domains)} domains"
                        )

                    if ips:
                        await ctx.emit(
                            event=EventType.IPS_EXPANDED.value,
                            targets=sorted(ips),
                            program_id=program_id,
                            confidence=0.9
                        )
                        self.logger.debug(
                            f"Emitted IPS_EXPANDED for {domain}: "
                            f"{len(ips)} IPs"
                        )

                    if cidrs:
                        await ctx.emit(
                            event=EventType.CIDR_DISCOVERED.value,
                            targets=sorted(cidrs),
                            program_id=program_id,
                            confidence=0.9
                        )
                        self.logger.debug(
                            f"Emitted CIDR_DISCOVERED for {domain}: "
                            f"{len(cidrs)} CIDRs"
                        )

                    if asns:
                        await ctx.emit(
                            event=EventType.ASN_DISCOVERED.value,
                            targets=sorted(asns),
                            program_id=program_id,
                            confidence=0.9
                        )
                        self.logger.debug(
                            f"Emitted ASN_DISCOVERED for {domain}: "
                            f"{len(asns)} ASNs"
                        )

                    return len(raw_domains), len(ips)
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
