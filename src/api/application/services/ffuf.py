import asyncio
import json
import logging
import re
from typing import List, Dict, Any
from urllib.parse import urlparse
from uuid import UUID

from api.application.dto.scan_dto import FFUFScanOutputDTO
from api.infrastructure.events.event_bus import EventBus
from api.infrastructure.events.event_types import EventType
from api.infrastructure.runners.ffuf_cli import FFUFCliRunner

logger = logging.getLogger(__name__)

STATIC_EXTENSIONS = {
    '.css', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.woff', '.woff2',
    '.ttf', '.eot', '.mp4', '.mp3', '.pdf', '.ico', '.webp', '.otf'
}


class FFUFScanService:
    """
    Service for FFUF directory/file fuzzing.
    Discovers hidden endpoints through fuzzing with wordlists.
    """

    def __init__(self, runner: FFUFCliRunner, bus: EventBus):
        self.runner = runner
        self.bus = bus

    async def execute(self, program_id: UUID, targets: List[str]) -> FFUFScanOutputDTO:
        """
        Execute FFUF fuzzing on target URLs.

        Args:
            program_id: Target program ID
            targets: List of base URLs to fuzz

        Returns:
            DTO with scan status
        """
        logger.info(f"Starting FFUF scan: program={program_id} targets={len(targets)}")

        asyncio.create_task(self._run_scan(program_id, targets))

        return FFUFScanOutputDTO(
            status="started",
            message=f"FFUF scan started for {len(targets)} target{'s' if len(targets) != 1 else ''}",
            scanner="ffuf",
            targets_count=len(targets),
        )

    async def _run_scan(self, program_id: UUID, targets: List[str]):
        """Background task for FFUF execution"""
        try:
            for target in targets:
                results = []

                async for event in self.runner.run(target):
                    if event.type == "stdout" and event.payload:
                        parsed = self._parse_ffuf_jsonline(event.payload)
                        if parsed:
                            results.append(parsed)

                if results:
                    filtered = self._filter_static_files(results)
                    if filtered:
                        await self._publish_results(program_id, filtered)

            logger.info(
                f"FFUF scan completed: program={program_id} targets={len(targets)}"
            )
        except Exception as e:
            logger.error(f"FFUF scan failed: program={program_id} error={e}")

    def _parse_ffuf_jsonline(self, line: str) -> Dict[str, Any] | None:
        """
        Parse single JSON line from FFUF output.

        Returns:
            Result dict with url, status, length, etc.
        """
        try:
            data = json.loads(line.strip())
            return {
                "url": data.get("url"),
                "status": data.get("status"),
                "length": data.get("length"),
                "words": data.get("words"),
                "lines": data.get("lines"),
                "content_type": data.get("content-type", ""),
                "redirect_location": data.get("redirectlocation", ""),
            }
        except json.JSONDecodeError:
            return None

    def _filter_static_files(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter out static files (.css, .js, images, etc)"""
        filtered = []

        for result in results:
            url = result.get("url", "")
            if not url:
                continue

            try:
                parsed = urlparse(url)
                path = parsed.path.lower()

                if any(path.endswith(ext) for ext in STATIC_EXTENSIONS):
                    continue

                filtered.append(result)
            except Exception:
                filtered.append(result)

        return filtered

    async def _publish_results(self, program_id: UUID, results: List[Dict[str, Any]]):
        """Publish discovered endpoints for ingestion"""
        await self.bus.publish(
            EventType.FFUF_RESULTS_BATCH,
            {
                "program_id": str(program_id),
                "results": results,
            },
        )
        logger.info(f"Published FFUF results: program={program_id} count={len(results)}")
