"""GAU discovered pipeline node - triggers HTTPX"""

from typing import Dict, Any
from uuid import UUID

from api.infrastructure.events.event_types import EventType
from api.application.pipeline.base import PipelineNode
from api.application.services.httpx import HTTPXScanService


class GAUDiscoveredNode(PipelineNode):
    """
    Handles GAU_DISCOVERED event.

    Role:
    - Filter URLs by scope
    - Trigger HTTPX scan on in-scope URLs
    - Publish HTTPX results as SCAN_RESULTS_BATCH events

    Event flow:
    IN:  GAU_DISCOVERED
    OUT: SCAN_RESULTS_BATCH
    """

    event_in = EventType.GAU_DISCOVERED
    event_out = [EventType.SCAN_RESULTS_BATCH]

    async def process(self, event: Dict[str, Any]) -> None:
        program_id = UUID(event["program_id"])
        urls = event["urls"]

        self.logger.info(
            f"GAU URLs discovered: program={program_id} count={len(urls)}"
        )

        in_scope, out_of_scope = await self.ctx.scope.filter_urls(program_id, urls)

        if out_of_scope:
            self.logger.info(
                f"Filtered out-of-scope URLs: program={program_id} "
                f"in_scope={len(in_scope)} out_of_scope={len(out_of_scope)}"
            )

        if not in_scope:
            self.logger.info(f"No in-scope URLs to scan: program={program_id}")
            return

        async with self.ctx.acquire_scan_slot():
            async with self.ctx.container() as request_container:
                httpx_service = await request_container.get(HTTPXScanService)

                self.logger.info(
                    f"Starting HTTPX scan on GAU URLs: "
                    f"program={program_id} urls={len(in_scope)}"
                )

                async for batch in httpx_service.execute(program_id=program_id, targets=in_scope):
                    await self.ctx.emit(
                        EventType.SCAN_RESULTS_BATCH,
                        {
                            "program_id": str(program_id),
                            "results": batch,
                        },
                    )
