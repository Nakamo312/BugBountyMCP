"""Legacy Subfinder scan service facade."""
from __future__ import annotations

import logging
from uuid import UUID

from api.application.dto.scan_dto import SubfinderScanOutputDTO
from api.application.services._legacy_scan import publish_legacy_event, resolve_awaitable
from api.infrastructure.events.event_types import EventType

logger = logging.getLogger(__name__)


class SubfinderScanService:
    def __init__(self, runner, processor, bus):
        self.runner = runner
        self.processor = processor
        self.bus = bus

    async def execute(self, program_id: UUID, domain: str) -> SubfinderScanOutputDTO:
        return SubfinderScanOutputDTO(
            status="started",
            message=f"Subfinder scan started for {domain}",
            scanner="subfinder",
            domain=domain,
        )

    async def _run_scan(self, program_id: UUID, domain: str) -> None:
        try:
            stream = await resolve_awaitable(self.runner.run(domain))
            batches = await resolve_awaitable(self.processor.batch_stream(stream))
            async for batch in batches:
                if batch:
                    await self._publish_batch(program_id, batch)
        except Exception:
            logger.exception("Subfinder scan failed")

    async def _publish_batch(self, program_id: UUID, subdomains: list[str]) -> None:
        await publish_legacy_event(
            self.bus,
            EventType.SUBDOMAIN_DISCOVERED,
            {"program_id": str(program_id), "subdomains": subdomains, "targets": subdomains},
        )
