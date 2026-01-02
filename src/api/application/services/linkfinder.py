import asyncio
import logging
from typing import List
from uuid import UUID

from api.application.dto.scan_dto import LinkFinderScanOutputDTO
from api.infrastructure.events.event_bus import EventBus
from api.infrastructure.events.event_types import EventType
from api.infrastructure.runners.linkfinder_cli import LinkFinderCliRunner

logger = logging.getLogger(__name__)


class LinkFinderScanService:
    """
    Service for LinkFinder JS analysis.
    Extracts endpoints from JavaScript files and publishes them to HTTPX for validation.
    """

    def __init__(self, runner: LinkFinderCliRunner, bus: EventBus):
        self.runner = runner
        self.bus = bus

    async def execute(self, program_id: UUID, targets: List[str]) -> LinkFinderScanOutputDTO:
        """
        Execute LinkFinder scan on JS files.

        Args:
            program_id: Target program ID
            targets: List of JS URLs to analyze

        Returns:
            DTO with scan status
        """
        logger.info(f"Starting LinkFinder scan: program={program_id} targets={len(targets)}")

        asyncio.create_task(self._run_scan(program_id, targets))

        return LinkFinderScanOutputDTO(
            status="started",
            message=f"LinkFinder scan started for {len(targets)} JS files",
            scanner="linkfinder",
            targets_count=len(targets)
        )

    async def _run_scan(self, program_id: UUID, targets: List[str]):
        """Background task for LinkFinder execution"""
        try:
            all_urls = []

            async for result in self.runner.run(targets):
                if result.type == "result" and result.payload:
                    urls = result.payload.get("urls", [])
                    all_urls.extend(urls)
                    logger.debug(
                        f"LinkFinder found URLs: source={result.payload.get('source_js')} count={len(urls)}"
                    )

            if all_urls:
                await self._publish_urls_for_httpx(program_id, all_urls)

            logger.info(
                f"LinkFinder scan completed: program={program_id} targets={len(targets)} "
                f"urls_found={len(all_urls)}"
            )
        except Exception as e:
            logger.error(f"LinkFinder scan failed: program={program_id} error={e}")

    async def _publish_urls_for_httpx(self, program_id: UUID, urls: List[str]):
        """Publish discovered URLs to HTTPX for validation"""
        await self.bus.publish(
            EventType.GAU_DISCOVERED,
            {
                "program_id": str(program_id),
                "urls": urls,
            },
        )
        logger.info(f"Published LinkFinder URLs for HTTPX validation: program={program_id} count={len(urls)}")
