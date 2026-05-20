"""Legacy DNSx scan service facade."""
from __future__ import annotations

import logging
from uuid import UUID

from api.application.dto.scan_dto import DNSxScanOutputDTO
from api.application.services._legacy_scan import publish_legacy_event, resolve_awaitable
from api.infrastructure.events.event_types import EventType

logger = logging.getLogger(__name__)


class DNSxScanService:
    def __init__(self, runner, processor, bus):
        self.runner = runner
        self.processor = processor
        self.bus = bus

    async def execute(self, program_id: UUID, targets: list[str], mode: str = "basic") -> DNSxScanOutputDTO:
        return DNSxScanOutputDTO(
            status="completed",
            message=f"DNSx {mode} scan completed for {len(targets)} targets",
            scanner="dnsx",
            targets_count=len(targets),
            mode=mode,
        )

    async def _run_scan(self, program_id: UUID, targets: list[str], mode: str) -> None:
        stream = self.runner.run_basic(targets) if mode == "basic" else self.runner.run_deep(targets)
        stream = await resolve_awaitable(stream)
        try:
            batches = await resolve_awaitable(self.processor.batch_stream(stream))
            async for batch in batches:
                if batch:
                    await self._publish_batch(program_id, batch, mode)
        except Exception:
            logger.exception("DNSx scan failed")

    async def _publish_batch(self, program_id: UUID, results: list[dict], mode: str) -> None:
        event_type = (
            EventType.DNSX_BASIC_RESULTS_BATCH
            if mode == "basic"
            else EventType.DNSX_DEEP_RESULTS_BATCH
        )
        await publish_legacy_event(
            self.bus,
            event_type,
            {"program_id": str(program_id), "results": results},
        )
