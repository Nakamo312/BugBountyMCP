"""DNSx filtered hosts pipeline node - triggers HTTPX"""

from typing import Dict, Any
from uuid import UUID

from api.infrastructure.events.event_types import EventType
from api.application.pipeline.base import PipelineNode
from api.application.services.httpx import HTTPXScanService


class DNSxFilteredHostsNode(PipelineNode):
    """
    Handles DNSX_FILTERED_HOSTS event.

    Role in DNS Track:
    - Trigger HTTPX scan on non-wildcard hosts
    - Publish HTTPX results as SCAN_RESULTS_BATCH events
    - Part of: DNSx Basic -> HTTPX pipeline

    Event flow:
    IN:  DNSX_FILTERED_HOSTS
    OUT: SCAN_RESULTS_BATCH
    """

    event_in = EventType.DNSX_FILTERED_HOSTS
    event_out = [EventType.SCAN_RESULTS_BATCH]

    async def process(self, event: Dict[str, Any]) -> None:
        program_id = UUID(event["program_id"])
        hosts = event["hosts"]

        self.logger.info(
            f"DNSx filtered hosts received: program={program_id} count={len(hosts)}"
        )

        async with self.ctx.acquire_scan_slot():
            async with self.ctx.container() as request_container:
                httpx_service = await request_container.get(HTTPXScanService)

                self.logger.info(
                    f"Starting HTTPX scan on filtered hosts: "
                    f"program={program_id} hosts={len(hosts)}"
                )

                async for batch in httpx_service.execute(program_id=program_id, targets=hosts):
                    await self.ctx.emit(
                        EventType.SCAN_RESULTS_BATCH,
                        {
                            "program_id": str(program_id),
                            "results": batch,
                        },
                    )
