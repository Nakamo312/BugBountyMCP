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
    Detects JS files and publishes them for LinkFinder analysis.
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
            js_files_collected = []

            async for batch in self.processor.batch_stream(self.runner.run(domain, include_subs)):
                if batch:
                    js_files_in_batch = [url for url in batch if self._is_js_file(url)]
                    js_files_collected.extend(js_files_in_batch)

                    await self._publish_batch(program_id, batch)
                    batches_published += 1
                    urls_found += len(batch)

            if js_files_collected:
                await self._publish_js_files(program_id, js_files_collected)

            logger.info(
                f"GAU scan completed: program={program_id} domain={domain} "
                f"urls={urls_found} batches={batches_published} js_files={len(js_files_collected)}"
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

    def _is_js_file(self, url: str) -> bool:
        """Check if URL points to a JavaScript file"""
        url_lower = url.lower()
        return url_lower.endswith('.js') or '.js?' in url_lower

    async def _publish_js_files(self, program_id: UUID, js_files: list[str]):
        """Publish discovered JS files for LinkFinder analysis"""
        await self.bus.publish(
            EventType.JS_FILES_DISCOVERED,
            {
                "program_id": str(program_id),
                "js_files": js_files,
            },
        )
        logger.debug(f"Published JS files for LinkFinder: program={program_id} count={len(js_files)}")
