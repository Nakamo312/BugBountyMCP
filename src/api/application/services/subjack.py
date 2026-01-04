"""Subjack scan service for subdomain takeover detection"""
import asyncio
import logging
from uuid import UUID

from api.infrastructure.runners.subjack_cli import SubjackCliRunner
from api.application.services.batch_processor import BaseBatchProcessor
from api.infrastructure.events.event_bus import EventBus
from api.infrastructure.events.event_types import EventType
from api.application.dto.scan_dto import ScanOutputDTO

logger = logging.getLogger(__name__)


class SubjackScanService:
    """
    Service for Subjack subdomain takeover detection.
    Publishes batched results to EventBus for SubjackResultIngestor.
    """

    def __init__(self, runner: SubjackCliRunner, processor: BaseBatchProcessor, bus: EventBus):
        self.runner = runner
        self.processor = processor
        self.bus = bus

    async def execute(
        self,
        program_id: UUID,
        targets: list[str] | str,
    ) -> ScanOutputDTO:
        """
        Execute Subjack subdomain takeover scan.

        Args:
            program_id: Target program ID
            targets: Single domain or list of domains to scan

        Returns:
            DTO with scan status
        """
        if isinstance(targets, str):
            targets = [targets]

        logger.info(f"Starting Subjack scan: program={program_id} targets={len(targets)}")

        asyncio.create_task(self._run_scan(program_id, targets))

        target_desc = targets[0] if len(targets) == 1 else f"{len(targets)} targets"
        return ScanOutputDTO(
            status="started",
            message=f"Subjack scan started for {target_desc}",
            scanner="subjack",
            target=target_desc,
        )

    async def _run_scan(self, program_id: UUID, targets: list[str]):
        """Background task for Subjack scan execution"""
        try:
            results_count = 0
            batches_published = 0

            async for batch in self.processor.batch_stream(self.runner.run(targets)):
                if batch:
                    await self._publish_batch(program_id, batch)
                    batches_published += 1
                    results_count += len(batch)

            logger.info(
                f"Subjack scan completed: program={program_id} targets={len(targets)} "
                f"vulnerabilities={results_count} batches={batches_published}"
            )
        except Exception as e:
            logger.error(f"Subjack scan failed: program={program_id} targets={len(targets)} error={e}")

    async def _publish_batch(self, program_id: UUID, results: list[dict]):
        """Publish result batch to EventBus for SubjackResultIngestor"""
        await self.bus.publish(
            EventType.SUBJACK_RESULTS_BATCH,
            {
                "program_id": str(program_id),
                "results": results,
            },
        )
        logger.debug(f"Published Subjack results batch: program={program_id} count={len(results)}")
