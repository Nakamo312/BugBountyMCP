"""Subfinder Scan Service - Event-driven architecture"""
import asyncio
import logging
from typing import AsyncIterator, List
from uuid import UUID

from api.application.dto import SubfinderScanOutputDTO
from api.infrastructure.events.event_bus import EventBus
from api.infrastructure.runners.subfinder_cli import SubfinderCliRunner

logger = logging.getLogger(__name__)


class SubfinderScanService:
    """
    Event-driven service for Subfinder scans.
    Publishes batches of discovered subdomains to EventBus for HTTPX processing.
    """

    BATCH_SIZE_MIN = 10
    BATCH_SIZE_MAX = 50
    BATCH_TIMEOUT = 5.0

    def __init__(self, runner: SubfinderCliRunner, bus: EventBus):
        self.runner = runner
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
            async for batch in self._batch_subdomains(domain):
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

    async def _batch_subdomains(self, domain: str) -> AsyncIterator[List[str]]:
        """
        Collect subdomains into optimally-sized batches.

        Yields:
            Batches of subdomains (10-50 domains per batch)
        """
        batch = []
        last_batch_time = asyncio.get_event_loop().time()

        async for event in self.runner.run(domain):
            if event.type == "subdomain" and event.payload:
                batch.append(event.payload)

                if len(batch) >= self.BATCH_SIZE_MAX:
                    yield batch
                    batch = []
                    last_batch_time = asyncio.get_event_loop().time()

                elif (len(batch) >= self.BATCH_SIZE_MIN and
                      asyncio.get_event_loop().time() - last_batch_time >= self.BATCH_TIMEOUT):
                    yield batch
                    batch = []
                    last_batch_time = asyncio.get_event_loop().time()

        if batch:
            yield batch

    async def _publish_batch(self, program_id: UUID, subdomains: List[str]):
        """
        Publish batch of subdomains to EventBus.

        Args:
            program_id: Program identifier
            subdomains: List of discovered subdomains
        """
        await self.bus.publish("subdomain_discovered", {
            "program_id": str(program_id),
            "subdomains": subdomains,
            "timestamp": asyncio.get_event_loop().time()
        })
