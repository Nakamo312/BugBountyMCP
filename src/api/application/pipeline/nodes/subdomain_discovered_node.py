"""Subdomain discovered pipeline node - triggers DNSx Basic"""

from typing import Dict, Any
from uuid import UUID

from api.infrastructure.events.event_types import EventType
from api.application.pipeline.base import PipelineNode
from api.application.services.dnsx import DNSxScanService


class SubdomainDiscoveredNode(PipelineNode):
    """
    Handles SUBDOMAIN_DISCOVERED event from Subfinder and other sources.

    Role in DNS Track:
    - Filter subdomains by scope
    - Trigger DNSx Basic (wildcard filter)
    - Publish DNSx results as DNSX_BASIC_RESULTS_BATCH events
    - Part of: Subfinder -> DNSx Basic -> HTTPX pipeline

    Event flow:
    IN:  SUBDOMAIN_DISCOVERED
    OUT: DNSX_BASIC_RESULTS_BATCH
    """

    event_in = EventType.SUBDOMAIN_DISCOVERED
    event_out = [EventType.DNSX_BASIC_RESULTS_BATCH]

    async def process(self, event: Dict[str, Any]) -> None:
        program_id = UUID(event["program_id"])
        subdomains = event["subdomains"]

        self.logger.info(
            f"Subdomains discovered: program={program_id} count={len(subdomains)}"
        )

        in_scope, out_of_scope = await self.ctx.scope.filter_domains(
            program_id, subdomains
        )

        if out_of_scope:
            self.logger.info(
                f"Filtered out-of-scope subdomains: program={program_id} "
                f"in_scope={len(in_scope)} out_of_scope={len(out_of_scope)}"
            )

        if not in_scope:
            self.logger.info(f"No in-scope subdomains: program={program_id}")
            return

        async with self.ctx.acquire_scan_slot():
            async with self.ctx.container() as request_container:
                dnsx_service = await request_container.get(DNSxScanService)

                self.logger.info(
                    f"Starting DNSx Basic scan: program={program_id} "
                    f"targets={len(in_scope)}"
                )

                async for batch in dnsx_service.execute(
                    program_id=program_id, targets=in_scope, mode="basic"
                ):
                    await self.ctx.emit(
                        EventType.DNSX_BASIC_RESULTS_BATCH,
                        {
                            "program_id": str(program_id),
                            "results": batch,
                        },
                    )
