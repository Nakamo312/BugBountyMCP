"""HTTPX Scan Service - Event-driven architecture"""
import asyncio
import logging
from typing import List, Dict, Any
from uuid import UUID

from api.application.dto import HTTPXScanOutputDTO
from api.infrastructure.events.event_bus import EventBus
from api.infrastructure.runners.httpx_cli import HTTPXCliRunner

logger = logging.getLogger(__name__)


class HTTPXScanService:
    """
    Event-driven service for HTTPX scans.
    Batches results before publishing to EventBus for better performance.
    """

    RESULT_BATCH_SIZE = 100
    RESULT_BATCH_TIMEOUT = 10.0

    def __init__(self, runner: HTTPXCliRunner, bus: EventBus):
        self.runner = runner
        self.bus = bus

    async def execute(self, program_id: UUID, targets: List[str]) -> HTTPXScanOutputDTO:
        """
        Execute HTTPX scan and publish results.
        Returns immediately, scan runs in background.

        Args:
            program_id: Program identifier
            targets: List of URLs or hosts to scan

        Returns:
            Immediate response that scan has started
        """
        logger.info(f"Starting HTTPX scan: program={program_id} targets={len(targets)}")

        asyncio.create_task(self._run_scan(program_id, targets))

        return HTTPXScanOutputDTO(
            status="started",
            message=f"HTTPX scan started for {len(targets)} targets",
            scanner="httpx",
            targets_count=len(targets)
        )

    async def _run_scan(self, program_id: UUID, targets: List[str]):
        """
        Background task that runs the actual scan with result batching.
        """
        results_count = 0
        batches_published = 0

        try:
            async for batch in self._batch_results(targets):
                if batch:
                    await self._publish_batch(program_id, batch)
                    batches_published += 1
                    results_count += len(batch)

            logger.info(
                f"HTTPX scan completed: program={program_id} "
                f"results={results_count} batches={batches_published}"
            )
        except Exception as e:
            logger.error(f"HTTPX scan failed: program={program_id} error={e}", exc_info=True)

    async def _batch_results(
        self,
        targets: List[str],
    ):
        """
        Collect HTTPX results and yield them in batches.
        Similar to GAU/Katana batching strategy.
        """
        batch: List[Dict[str, Any]] = []
        last_batch_time = asyncio.get_event_loop().time()

        async for event in self.runner.run(targets):
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
        """Publish batch of results to EventBus"""
        await self.bus.publish(
            "scan_results_batch",
            {
                "program_id": str(program_id),
                "results": results,
            },
        )
        logger.debug(f"Published HTTPX results batch: program={program_id} count={len(results)}")
