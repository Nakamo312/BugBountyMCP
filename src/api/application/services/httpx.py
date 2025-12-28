"""HTTPX Scan Service - Event-driven architecture"""
import asyncio
import logging
from typing import List
from uuid import UUID

from api.application.dto import HTTPXScanOutputDTO
from api.infrastructure.events.event_bus import EventBus
from api.infrastructure.runners.httpx_cli import HTTPXCliRunner

logger = logging.getLogger(__name__)


class HTTPXScanService:
    """
    Event-driven service for HTTPX scans.
    Publishes results to EventBus as they are discovered.
    """

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
        Background task that runs the actual scan.
        """
        results_count = 0

        try:
            async for event in self.runner.run(targets):
                if event.type == "result" and event.payload:
                    await self.bus.publish("scan_results", {
                        "program_id": str(program_id),
                        "result": event.payload
                    })
                    results_count += 1

            logger.info(f"HTTPX scan completed: program={program_id} results={results_count}")
        except Exception as e:
            logger.error(f"HTTPX scan failed: program={program_id} error={e}", exc_info=True)
