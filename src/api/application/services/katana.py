"""Katana scan service for web crawling"""
import asyncio
import logging
from uuid import UUID
from typing import Set

from api.infrastructure.runners.katana_cli import KatanaCliRunner
from api.infrastructure.events.event_bus import EventBus
from api.application.dto.scan_dto import KatanaScanOutputDTO

logger = logging.getLogger(__name__)


class KatanaScanService:
    """
    Service for Katana web crawling.
    Discovers URLs via active crawling, deduplicates, and publishes batches to EventBus.
    """

    BATCH_SIZE_MIN = 10
    BATCH_SIZE_MAX = 50
    BATCH_TIMEOUT = 5.0

    def __init__(self, runner: KatanaCliRunner, bus: EventBus):
        self.runner = runner
        self.bus = bus

    async def execute(
        self,
        program_id: UUID,
        target: str,
        depth: int = 3,
        js_crawl: bool = True,
        headless: bool = False,
    ) -> KatanaScanOutputDTO:
        """
        Execute Katana crawl for target URL.

        Args:
            program_id: Target program ID
            target: Target URL to crawl
            depth: Maximum crawl depth (default: 3)
            js_crawl: Enable JavaScript crawling (default: True)
            headless: Enable headless browser mode (default: False)

        Returns:
            DTO with scan status
        """
        logger.info(
            f"Starting Katana scan: program={program_id} target={target} "
            f"depth={depth} js_crawl={js_crawl} headless={headless}"
        )

        asyncio.create_task(self._run_scan(program_id, target, depth, js_crawl, headless))

        return KatanaScanOutputDTO(
            status="started",
            message=f"Katana crawl started for {target}",
            scanner="katana",
            target=target,
        )

    async def _run_scan(
        self,
        program_id: UUID,
        target: str,
        depth: int,
        js_crawl: bool,
        headless: bool,
    ):
        """Background task for Katana crawl execution"""
        try:
            urls_found = 0
            batches_published = 0
            seen_urls: Set[str] = set()

            async for batch in self._batch_urls(program_id, target, depth, js_crawl, headless, seen_urls):
                if batch:
                    await self._publish_batch(program_id, batch)
                    batches_published += 1
                    urls_found += len(batch)

            logger.info(
                f"Katana scan completed: program={program_id} target={target} "
                f"urls={urls_found} batches={batches_published}"
            )
        except Exception as e:
            logger.error(f"Katana scan failed: program={program_id} target={target} error={e}")

    async def _batch_urls(
        self,
        program_id: UUID,
        target: str,
        depth: int,
        js_crawl: bool,
        headless: bool,
        seen_urls: Set[str],
    ):
        """
        Collect URLs from katana and yield them in batches.
        Deduplicates URLs in-memory.
        """
        batch = []
        last_batch_time = asyncio.get_event_loop().time()

        async for event in self.runner.run(target, depth, js_crawl, headless):
            if event.type != "url":
                continue

            url = event.payload
            if url in seen_urls:
                continue

            seen_urls.add(url)
            batch.append(url)

            current_time = asyncio.get_event_loop().time()
            time_elapsed = current_time - last_batch_time

            if len(batch) >= self.BATCH_SIZE_MAX or (
                len(batch) >= self.BATCH_SIZE_MIN and time_elapsed >= self.BATCH_TIMEOUT
            ):
                yield batch
                batch = []
                last_batch_time = current_time

        if batch:
            yield batch

    async def _publish_batch(self, program_id: UUID, urls: list[str]):
        """Publish URL batch to EventBus for HTTPX processing"""
        await self.bus.publish(
            "katana_discovered",
            {
                "program_id": str(program_id),
                "urls": urls,
            },
        )
        logger.debug(f"Published URL batch: program={program_id} count={len(urls)}")
