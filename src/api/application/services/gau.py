"""Legacy GAU scan service facade."""
from __future__ import annotations

from uuid import UUID

from api.application.dto.scan_dto import GAUScanOutputDTO
from api.application.services._legacy_scan import publish_legacy_event, resolve_awaitable
from api.infrastructure.events.event_types import EventType


class GAUScanService:
    def __init__(self, runner, processor, bus):
        self.runner = runner
        self.processor = processor
        self.bus = bus

    async def execute(self, program_id: UUID, domain: str, include_subs: bool = True) -> GAUScanOutputDTO:
        return GAUScanOutputDTO(
            status="started",
            message=f"GAU scan started for {domain}",
            scanner="gau",
            domain=domain,
        )

    async def _run_scan(self, program_id: UUID, domain: str, include_subs: bool = True) -> None:
        stream = await resolve_awaitable(self.runner.run([domain], include_subs=include_subs))
        batches = await resolve_awaitable(self.processor.batch_stream(stream))
        async for batch in batches:
            if batch:
                await self._publish_batch(program_id, batch)

    async def _publish_batch(self, program_id: UUID, urls: list[str]) -> None:
        await publish_legacy_event(
            self.bus,
            EventType.GAU_DISCOVERED,
            {"program_id": str(program_id), "urls": urls, "targets": urls},
        )
