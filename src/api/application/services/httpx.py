# application/services/httpx_service.py
from typing import List
import logging

from api.infrastructure.runners.httpx_cli import HTTPXCliRunner
from src.api.infrastructure.events.event_bus import EventBus

logger = logging.getLogger(__name__)

class HTTPXScanService:
    """
    Service that executes HTTPX scans and publishes results to a queue.
    Can run independently or as part of a pipeline.
    """
    def __init__(self, runner: HTTPXCliRunner, bus: EventBus):
        self.runner = runner
        self.bus = bus

    async def execute(self, program_id: str, targets: List[str]):
        """
        Execute scan for the given targets and publish each result asynchronously.

        Args:
            program_id: Identifier of the program.
            targets: List of URLs or hosts to scan.
        """
        logger.info("Starting HTTPX scan: program=%s targets=%s", program_id, targets)

        async for event in self.runner.run(targets):
            if hasattr(event, "payload"):
                await self.bus.publish("scan_results", {
                    "program_id": str(program_id),
                    "result": event.payload
                })

        logger.info("HTTPX scan finished: program=%s", program_id)
