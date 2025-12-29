"""Subfinder Scan Service - Event-driven architecture"""
import asyncio
import logging
from typing import List
from uuid import UUID

from api.application.dto import SubfinderScanOutputDTO
from api.application.services.batch_processor import SubfinderBatchProcessor
from api.infrastructure.events.event_bus import EventBus
from api.infrastructure.events.event_types import EventType
from api.infrastructure.runners.subfinder_cli import SubfinderCliRunner

logger = logging.getLogger(__name__)


class SubfinderScanService:
    """
    Event-driven service for Subfinder scans.
    Publishes batches of discovered subdomains to EventBus for HTTPX processing.
    """

    def __init__(self, runner: SubfinderCliRunner, processor: SubfinderBatchProcessor, bus: EventBus):
        self.runner = runner
        self.processor = processor
        self.bus = bus

    async def execute(self, program_id: UUID, domain: str) -> SubfinderScanOutputDTO:
        """
        Execute Subfinder scan and publish discovered subdomains in batches.
        Returns immediately, scan runs in background.

        Args:
            program_id: Program identifier
            domain: Target domain for subdomain enumeration

        Returns:
            Immediate response that scan has started
        """
        logger.info(f"Starting Subfinder scan: program={program_id} domain={domain}")

        asyncio.create_task(self._run_scan(program_id, domain))

        return SubfinderScanOutputDTO(
            status="started",
            message=f"Subfinder scan started for {domain}",
            scanner="subfinder",
            domain=domain
        )

    async def _run_scan(self, program_id: UUID, domain: str):
        """
        Background task that runs the actual scan.
        """
        total_subdomains = 0
        batches_published = 0

        try:
            async for batch in self.processor.batch_stream(self.runner.run(domain)):
                if batch:
                    await self._publish_batch(program_id, batch)
                    total_subdomains += len(batch)
                    batches_published += 1
                    logger.debug(f"Published batch {batches_published} with {len(batch)} subdomains")

            logger.info(
                f"Subfinder scan completed: program={program_id} domain={domain} "
                f"subdomains={total_subdomains} batches={batches_published}"
            )
        except Exception as e:
            logger.error(f"Subfinder scan failed: program={program_id} domain={domain} error={e}", exc_info=True)

    async def _publish_batch(self, program_id: UUID, subdomains: List[str]):
        """
        Publish batch of subdomains to EventBus.

        Args:
            program_id: Program identifier
            subdomains: List of discovered subdomains
        """
        await self.bus.publish(EventType.SUBDOMAIN_DISCOVERED, {
            "program_id": str(program_id),
            "subdomains": subdomains,
            "timestamp": asyncio.get_event_loop().time()
        })
