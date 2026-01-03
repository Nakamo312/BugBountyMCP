import asyncio
import logging
import re
from typing import List, Dict, Any
from uuid import UUID

from api.application.dto.scan_dto import MantraScanOutputDTO
from api.infrastructure.events.event_bus import EventBus
from api.infrastructure.events.event_types import EventType
from api.infrastructure.runners.mantra_cli import MantraCliRunner

logger = logging.getLogger(__name__)


class MantraScanService:
    """
    Service for Mantra secret scanning.
    Analyzes JavaScript files for leaked secrets and credentials.
    """

    def __init__(self, runner: MantraCliRunner, bus: EventBus):
        self.runner = runner
        self.bus = bus

    async def execute(self, program_id: UUID, targets: List[str]) -> MantraScanOutputDTO:
        """
        Execute Mantra scan on JS files.

        Args:
            program_id: Target program ID
            targets: List of JS URLs to scan

        Returns:
            DTO with scan status
        """
        logger.info(f"Starting Mantra scan: program={program_id} targets={len(targets)}")

        asyncio.create_task(self._run_scan(program_id, targets))

        return MantraScanOutputDTO(
            status="started",
            message=f"Mantra scan started for {len(targets)} JS file{'s' if len(targets) != 1 else ''}",
            scanner="mantra",
            targets_count=len(targets),
        )

    async def _run_scan(self, program_id: UUID, targets: List[str]):
        """Background task for Mantra execution"""
        try:
            results = []

            async for event in self.runner.run(targets):
                if event.type == "stdout" and event.payload:
                    parsed = self._parse_mantra_output(event.payload)
                    if parsed:
                        results.append(parsed)

            if results:
                await self._publish_results(program_id, results)

            logger.info(
                f"Mantra scan completed: program={program_id} targets={len(targets)} "
                f"secrets_found={len(results)}"
            )
        except Exception as e:
            logger.error(f"Mantra scan failed: program={program_id} error={e}")

    def _parse_mantra_output(self, line: str) -> Dict[str, Any] | None:
        """
        Parse Mantra output line.

        Format: [+] https://example.com/app.js [secret_value]

        Returns:
            Dict with url and secret, or None if not a valid secret line
        """
        ansi_escape = re.compile(r'\x1b\[[0-9;]*m')
        clean_line = ansi_escape.sub('', line).strip()

        match = re.match(r'^\[\+\]\s+(https?://[^\s]+)\s+\[(.+)\]$', clean_line)
        if match:
            return {
                "url": match.group(1),
                "secret": match.group(2),
            }
        return None

    async def _publish_results(self, program_id: UUID, results: List[Dict[str, Any]]):
        """Publish discovered secrets for ingestion"""
        await self.bus.publish(
            EventType.MANTRA_RESULTS_BATCH,
            {
                "program_id": str(program_id),
                "results": results,
            },
        )
        logger.info(f"Published Mantra results: program={program_id} count={len(results)}")
