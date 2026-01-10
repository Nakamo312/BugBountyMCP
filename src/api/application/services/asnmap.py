"""ASNMap Scan Service - Event-driven architecture"""

import logging
from uuid import UUID

from api.application.dto import ASNMapScanOutputDTO
from api.application.services.batch_processor import ASNMapBatchProcessor
from api.infrastructure.events.event_bus import EventBus
from api.infrastructure.events.event_types import EventType
from api.infrastructure.runners.asnmap_cli import ASNMapCliRunner

logger = logging.getLogger(__name__)


class ASNMapScanService:
    """
    Event-driven service for ASNMap scans.
    Batches results before publishing to EventBus for better performance.
    Supports three modes: domain, asn, organization.
    """

    def __init__(self, runner: ASNMapCliRunner, processor: ASNMapBatchProcessor, bus: EventBus):
        self.runner = runner
        self.processor = processor
        self.bus = bus

    async def execute(
        self,
        program_id: UUID,
        targets: list[str],
        mode: str = "domain"
    ) -> ASNMapScanOutputDTO:
        """
        Execute ASNMap scan and publish results.
        Blocks until scan completes to properly hold orchestrator semaphore.

        Args:
            program_id: Program identifier
            targets: List of targets (domains, ASNs, or organization names)
            mode: Scan mode - 'domain', 'asn', or 'organization'

        Returns:
            Response after scan has completed
        """
        logger.info(f"Starting ASNMap {mode} scan: program={program_id} targets={len(targets)}")

        await self._run_scan(program_id, targets, mode)

        return ASNMapScanOutputDTO(
            status="completed",
            message=f"ASNMap {mode} scan completed for {len(targets)} targets",
            scanner="asnmap",
            mode=mode,
            targets_count=len(targets)
        )

    async def _run_scan(self, program_id: UUID, targets: list[str], mode: str):
        """Run the actual scan with result batching"""
        results_count = 0
        batches_published = 0

        try:
            if mode == "domain":
                stream = self.runner.run_domain(targets)
            elif mode == "asn":
                stream = self.runner.run_asn(targets)
            elif mode == "organization":
                stream = self.runner.run_organization(targets)
            else:
                raise ValueError(f"Invalid ASNMap mode: {mode}. Must be 'domain', 'asn', or 'organization'")

            async for batch in self.processor.batch_stream(stream):
                if batch:
                    await self._publish_batch(program_id, batch)
                    batches_published += 1
                    results_count += len(batch)

            logger.info(
                f"ASNMap {mode} scan completed: program={program_id} "
                f"results={results_count} batches={batches_published}"
            )
        except Exception as e:
            logger.error(f"ASNMap {mode} scan failed: program={program_id} error={e}", exc_info=True)
            raise

    async def _publish_batch(self, program_id: UUID, results: list[dict]):
        """Publish batch of results to EventBus"""
        await self.bus.publish(
            EventType.ASNMAP_RESULTS_BATCH,
            {
                "program_id": str(program_id),
                "results": results,
            },
        )
        logger.debug(f"Published ASNMap results batch: program={program_id} count={len(results)}")
