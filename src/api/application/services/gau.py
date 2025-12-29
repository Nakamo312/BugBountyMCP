"""GAU scan service for URL enumeration"""
import asyncio
import logging
from uuid import UUID
from typing import Set

from api.infrastructure.runners.gau_cli import GAUCliRunner
from api.infrastructure.events.event_bus import EventBus
from api.application.dto.scan_dto import GAUScanOutputDTO

logger = logging.getLogger(__name__)


class GAUScanService:
    """
    Service for GAU (GetAllURLs) scanning.
    Discovers URLs from web archives, deduplicates, and publishes batches to EventBus.
    """

    BATCH_SIZE_MIN = 50
    BATCH_SIZE_MAX = 100
    BATCH_TIMEOUT = 10.0

    def __init__(self, runner: GAUCliRunner, bus: EventBus):
        self.runner = runner
        self.bus = bus

    async def execute(self, program_id: UUID, domain: str, include_subs: bool = True) -> GAUScanOutputDTO:
        """
        Execute GAU scan for domain.

        Args:
            program_id: Target program ID
            domain: Domain to scan
            include_subs: Include subdomains in results

        Returns:
            DTO with scan status
        """
        logger.info(f"Starting GAU scan: program={program_id} domain={domain} include_subs={include_subs}")

        asyncio.create_task(self._run_scan(program_id, domain, include_subs))

        return GAUScanOutputDTO(
            status="started",
            message=f"GAU scan started for {domain}",
            scanner="gau",
            domain=domain,
        )

    async def _run_scan(self, program_id: UUID, domain: str, include_subs: bool):
        """Background task for GAU scan execution"""
        try:
            urls_found = 0
            batches_published = 0
            seen_urls: Set[str] = set()

            async for batch in self._batch_urls(program_id, domain, include_subs, seen_urls):
                if batch:
                    await self._publish_batch(program_id, batch)
                    batches_published += 1
                    urls_found += len(batch)

            logger.info(
                f"GAU scan completed: program={program_id} domain={domain} "
                f"urls={urls_found} batches={batches_published}"
            )
        except Exception as e:
            logger.error(f"GAU scan failed: program={program_id} domain={domain} error={e}")

    async def _batch_urls(self, program_id: UUID, domain: str, include_subs: bool, seen_urls: Set[str]):
        """
        Collect URLs from gau and yield them in batches.
        Deduplicates URLs in-memory.
        """
        batch = []
        last_batch_time = asyncio.get_event_loop().time()

        async for event in self.runner.run(domain, include_subs):
            if event.type != "url":
                continue

            url = event.payload
            if url in seen_urls:
                continue

            seen_urls.add(url)
            batch.append(url)

            current_time = asyncio.get_event_loop().time()
            time_elapsed = current_time - last_batch_time

            if len(batch) >= self.BATCH_SIZE_MAX or (len(batch) >= self.BATCH_SIZE_MIN and time_elapsed >= self.BATCH_TIMEOUT):
                yield batch
                batch = []
                last_batch_time = current_time

        if batch:
            yield batch

    async def _publish_batch(self, program_id: UUID, urls: list[str]):
        """Publish URL batch to EventBus for HTTPX processing"""
        await self.bus.publish(
            "gau_discovered",
            {
                "program_id": str(program_id),
                "urls": urls,
            },
        )
        logger.debug(f"Published URL batch: program={program_id} count={len(urls)}")
