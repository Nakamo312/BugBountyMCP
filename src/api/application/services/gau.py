"""GAU scan service for URL enumeration"""
import asyncio
import logging
from uuid import UUID

from api.infrastructure.runners.gau_cli import GAUCliRunner
from api.application.services.batch_processor import GAUBatchProcessor
from api.infrastructure.events.event_bus import EventBus
from api.infrastructure.events.event_types import EventType
from api.application.dto.scan_dto import GAUScanOutputDTO

logger = logging.getLogger(__name__)


class GAUScanService:
    """
    Service for GAU (GetAllURLs) scanning.
    Discovers URLs from web archives, deduplicates, and publishes batches to EventBus.
    """

    def __init__(self, runner: GAUCliRunner, processor: GAUBatchProcessor, bus: EventBus):
        self.runner = runner
        self.processor = processor
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

            async for batch in self.processor.batch_stream(self.runner.run(domain, include_subs)):
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

    async def _publish_batch(self, program_id: UUID, urls: list[str]):
        """Publish URL batch to EventBus for HTTPX processing"""
        await self.bus.publish(
            EventType.GAU_DISCOVERED,
            {
                "program_id": str(program_id),
                "urls": urls,
            },
        )
        logger.debug(f"Published URL batch: program={program_id} count={len(urls)}")
