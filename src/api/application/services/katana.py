"""Katana scan service for web crawling"""
import asyncio
import logging
from uuid import UUID
from typing import Dict, Any, List

from api.infrastructure.runners.katana_cli import KatanaCliRunner
from api.infrastructure.events.event_bus import EventBus
from api.application.dto.scan_dto import KatanaScanOutputDTO

logger = logging.getLogger(__name__)


class KatanaScanService:
    """
    Service for Katana web crawling.
    Publishes batched JSON results to EventBus for KatanaResultIngestor.
    """

    RESULT_BATCH_SIZE = 100
    RESULT_BATCH_TIMEOUT = 10.0

    def __init__(self, runner: KatanaCliRunner, bus: EventBus):
        self.runner = runner
        self.bus = bus

    async def execute(
        self,
        program_id: UUID,
        targets: list[str] | str,
        depth: int = 3,
        js_crawl: bool = True,
        headless: bool = False,
    ) -> KatanaScanOutputDTO:
        """
        Execute Katana crawl for target URLs.

        Args:
            program_id: Target program ID
            targets: Single target URL or list of target URLs to crawl
            depth: Maximum crawl depth (default: 3)
            js_crawl: Enable JavaScript crawling (default: True)
            headless: Enable headless browser mode (default: False)

        Returns:
            DTO with scan status
        """
        if isinstance(targets, str):
            targets = [targets]

        logger.info(
            f"Starting Katana scan: program={program_id} targets={len(targets)} "
            f"depth={depth} js_crawl={js_crawl} headless={headless}"
        )

        asyncio.create_task(self._run_scan(program_id, targets, depth, js_crawl, headless))

        target_desc = targets[0] if len(targets) == 1 else f"{len(targets)} targets"
        return KatanaScanOutputDTO(
            status="started",
            message=f"Katana crawl started for {target_desc}",
            scanner="katana",
            target=target_desc,
        )

    async def _run_scan(
        self,
        program_id: UUID,
        targets: list[str],
        depth: int,
        js_crawl: bool,
        headless: bool,
    ):
        """Background task for Katana crawl execution"""
        try:
            results_count = 0
            batches_published = 0

            async for batch in self._batch_results(targets, depth, js_crawl, headless):
                if batch:
                    await self._publish_batch(program_id, batch)
                    batches_published += 1
                    results_count += len(batch)

            logger.info(
                f"Katana scan completed: program={program_id} targets={len(targets)} "
                f"results={results_count} batches={batches_published}"
            )
        except Exception as e:
            logger.error(f"Katana scan failed: program={program_id} targets={len(targets)} error={e}")

    async def _batch_results(
        self,
        targets: list[str],
        depth: int,
        js_crawl: bool,
        headless: bool,
    ):
        """
        Collect Katana JSON results and yield them in batches.
        """
        batch: List[Dict[str, Any]] = []
        last_batch_time = asyncio.get_event_loop().time()

        async for event in self.runner.run(targets, depth, js_crawl, headless):
            if event.type != "result" or not event.payload:
                continue

            batch.append(event.payload)

            current_time = asyncio.get_event_loop().time()
            time_elapsed = current_time - last_batch_time

            if len(batch) >= self.RESULT_BATCH_SIZE or time_elapsed >= self.RESULT_BATCH_TIMEOUT:
                yield batch
                batch = []
                last_batch_time = current_time

        if batch:
            yield batch

    async def _publish_batch(self, program_id: UUID, results: List[Dict[str, Any]]):
        """Publish result batch to EventBus for KatanaResultIngestor"""
        await self.bus.publish(
            "katana_results_batch",
            {
                "program_id": str(program_id),
                "results": results,
            },
        )
        logger.debug(f"Published Katana results batch: program={program_id} count={len(results)}")
