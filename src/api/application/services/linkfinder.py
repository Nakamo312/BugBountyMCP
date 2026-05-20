"""Legacy LinkFinder scan service facade."""
from __future__ import annotations

import logging
from uuid import UUID

from api.application.dto.scan_dto import LinkFinderScanOutputDTO
from api.application.services._legacy_scan import publish_legacy_event
from api.infrastructure.events.event_types import EventType

logger = logging.getLogger(__name__)


class LinkFinderScanService:
    def __init__(self, runner, bus):
        self.runner = runner
        self.bus = bus

    async def execute(self, program_id: UUID, targets: list[str]) -> LinkFinderScanOutputDTO:
        return LinkFinderScanOutputDTO(
            status="started",
            message=f"LinkFinder scan started for {len(targets)} JS files",
            scanner="linkfinder",
            targets_count=len(targets),
        )

    async def _run_scan(self, program_id: UUID, targets: list[str]) -> None:
        urls: list[str] = []
        try:
            async for event in self.runner.run(targets):
                if event.type != "result" or not event.payload:
                    continue
                urls.extend(event.payload.get("urls", []))
        except Exception:
            logger.exception("LinkFinder scan failed")
            return

        if urls:
            await self._publish_urls_for_httpx(program_id, urls)

    async def _publish_urls_for_httpx(self, program_id: UUID, urls: list[str]) -> None:
        await publish_legacy_event(
            self.bus,
            EventType.GAU_DISCOVERED,
            {"program_id": str(program_id), "urls": urls, "targets": urls},
        )
