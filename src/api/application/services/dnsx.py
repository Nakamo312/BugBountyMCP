"""DNSx Scan Service - Event-driven architecture"""
import logging
from uuid import UUID

from api.application.dto import DNSxScanOutputDTO
from api.application.services.batch_processor import DNSxBatchProcessor
from api.infrastructure.events.event_bus import EventBus
from api.infrastructure.events.event_types import EventType
from api.infrastructure.runners.dnsx_cli import DNSxCliRunner

logger = logging.getLogger(__name__)


class DNSxScanService:
    """
    Event-driven service for DNSx scans.
    Batches results before publishing to EventBus for better performance.
    Supports two modes: basic (A/AAAA/CNAME) and deep (all records).
    """

    def __init__(self, runner: DNSxCliRunner, processor: DNSxBatchProcessor, bus: EventBus):
        self.runner = runner
        self.processor = processor
        self.bus = bus

    async def execute(self, program_id: UUID, targets: list[str], mode: str = "basic") -> DNSxScanOutputDTO:
        """
        Execute DNSx scan and publish results.
        Blocks until scan completes to properly hold orchestrator semaphore.

        Args:
            program_id: Program identifier
            targets: List of domains/hosts to scan
            mode: Scan mode - 'basic' or 'deep'

        Returns:
            Response after scan has completed
        """
        logger.info(f"Starting DNSx {mode} scan: program={program_id} targets={len(targets)}")

        await self._run_scan(program_id, targets, mode)

        return DNSxScanOutputDTO(
            status="completed",
            message=f"DNSx {mode} scan completed for {len(targets)} targets",
            scanner="dnsx",
            targets_count=len(targets),
            mode=mode
        )

    async def _run_scan(self, program_id: UUID, targets: list[str], mode: str):
        """Run the actual scan with result batching"""
        results_count = 0
        batches_published = 0

        try:
            if mode == "basic":
                stream = self.runner.run_basic(targets)
            else:
                stream = self.runner.run_deep(targets)

            async for batch in self.processor.batch_stream(stream):
                if batch:
                    await self._publish_batch(program_id, batch, mode)
                    batches_published += 1
                    results_count += len(batch)

            logger.info(
                f"DNSx {mode} scan completed: program={program_id} "
                f"results={results_count} batches={batches_published}"
            )
        except Exception as e:
            logger.error(f"DNSx {mode} scan failed: program={program_id} error={e}", exc_info=True)

    async def _publish_batch(self, program_id: UUID, results: list[dict], mode: str):
        """Publish batch of results to EventBus"""
        event_type = EventType.DNSX_BASIC_RESULTS_BATCH if mode == "basic" else EventType.DNSX_DEEP_RESULTS_BATCH

        await self.bus.publish(
            event_type,
            {
                "program_id": str(program_id),
                "results": results,
            },
        )
        logger.debug(f"Published DNSx {mode} results batch: program={program_id} count={len(results)}")
