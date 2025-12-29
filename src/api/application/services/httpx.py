"""HTTPX Scan Service - Event-driven architecture"""
import asyncio
import logging
from typing import List, Dict, Any
from uuid import UUID

from api.application.dto import HTTPXScanOutputDTO
from api.application.services.batch_processor import HTTPXBatchProcessor
from api.infrastructure.events.event_bus import EventBus
from api.infrastructure.events.event_types import EventType
from api.infrastructure.runners.httpx_cli import HTTPXCliRunner

logger = logging.getLogger(__name__)


class HTTPXScanService:
    """
    Event-driven service for HTTPX scans.
    Batches results before publishing to EventBus for better performance.
    """

    def __init__(self, runner: HTTPXCliRunner, processor: HTTPXBatchProcessor, bus: EventBus):
        self.runner = runner
        self.processor = processor
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
            async for batch in self.processor.batch_stream(self.runner.run(targets)):
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

    async def _publish_batch(self, program_id: UUID, results: List[Dict[str, Any]]):
        """Publish batch of results to EventBus"""
        await self.bus.publish(
            EventType.SCAN_RESULTS_BATCH,
            {
                "program_id": str(program_id),
                "results": results,
            },
        )
        logger.debug(f"Published HTTPX results batch: program={program_id} count={len(results)}")
