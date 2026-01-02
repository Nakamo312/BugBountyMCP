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
    Extracts endpoints from JavaScript files and publishes results to EventBus.
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
            results_count = 0

            async for result in self.runner.run(targets):
                if result.type == "result" and result.payload:
                    await self._publish_result(program_id, result.payload)
                    results_count += len(result.payload.get("urls", []))

            logger.info(
                f"LinkFinder scan completed: program={program_id} targets={len(targets)} "
                f"urls_found={results_count}"
            )
        except Exception as e:
            logger.error(f"LinkFinder scan failed: program={program_id} error={e}")

    async def _publish_result(self, program_id: UUID, payload: dict):
        """Publish result to EventBus for LinkFinderResultIngestor"""
        await self.bus.publish(
            EventType.LINKFINDER_RESULTS,
            {
                "program_id": str(program_id),
                "result": payload,
            },
        )
        logger.debug(
            f"Published LinkFinder result: program={program_id} "
            f"source={payload.get('source_js')} urls={len(payload.get('urls', []))}"
        )
