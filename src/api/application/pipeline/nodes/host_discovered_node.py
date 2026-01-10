"""Host discovered pipeline node - triggers Katana or DNSx Deep"""

from typing import Dict, Any
from uuid import UUID
import asyncio

from api.infrastructure.events.event_types import EventType
from api.application.pipeline.base import PipelineNode
from api.application.services.katana import KatanaScanService
from api.application.services.dnsx import DNSxScanService


class HostDiscoveredNode(PipelineNode):
    """
    Handles HOST_DISCOVERED event.

    Role in DNS Track:
    - If source=httpx_for_dnsx_deep -> trigger DNSx Deep, publish DNSX_DEEP_RESULTS_BATCH
    - Otherwise -> trigger Katana crawl, publish KATANA_RESULTS_BATCH (with scope filter and delay)

    Event flow:
    IN:  HOST_DISCOVERED
    OUT: DNSX_DEEP_RESULTS_BATCH or KATANA_RESULTS_BATCH
    """

    event_in = EventType.HOST_DISCOVERED
    event_out = [EventType.DNSX_DEEP_RESULTS_BATCH, EventType.KATANA_RESULTS_BATCH]

    async def process(self, event: Dict[str, Any]) -> None:
        program_id = event["program_id"]
        hosts = event["hosts"]
        source = event.get("source", "httpx")

        self.logger.info(
            f"Hosts discovered: program={program_id} count={len(hosts)} source={source}"
        )

        if source == "httpx_for_dnsx_deep":
            await self._trigger_dnsx_deep(program_id, hosts)
        else:
            await self._trigger_katana(program_id, hosts)

    async def _trigger_dnsx_deep(self, program_id: str, hosts: list[str]):
        """Trigger DNSx Deep scan for live hosts"""
        async with self.ctx.acquire_scan_slot():
            async with self.ctx.container() as request_container:
                dnsx_service = await request_container.get(DNSxScanService)

                self.logger.info(
                    f"Starting DNSx Deep scan: program={program_id} hosts={len(hosts)}"
                )

                async for batch in dnsx_service.execute(
                    program_id=UUID(program_id), targets=hosts, mode="deep"
                ):
                    await self.ctx.emit(
                        EventType.DNSX_DEEP_RESULTS_BATCH,
                        {
                            "program_id": program_id,
                            "results": batch,
                        },
                    )

    async def _trigger_katana(self, program_id: str, hosts: list[str]):
        """Trigger Katana crawl with scope filter and delay"""
        await asyncio.sleep(self.ctx.get_scan_delay())

        program_uuid = UUID(program_id)
        in_scope, out_of_scope = await self.ctx.scope.filter_domains(
            program_uuid, hosts
        )

        if out_of_scope:
            self.logger.info(
                f"Filtered out-of-scope hosts for Katana: program={program_id} "
                f"in_scope={len(in_scope)} out_of_scope={len(out_of_scope)}"
            )

        if not in_scope:
            self.logger.info(f"No in-scope hosts to crawl: program={program_id}")
            return

        async with self.ctx.acquire_scan_slot():
            async with self.ctx.container() as request_container:
                katana_service = await request_container.get(KatanaScanService)

                self.logger.info(
                    f"Starting Katana crawl: program={program_id} hosts={len(in_scope)}"
                )

                async for batch in katana_service.execute(program_id=program_uuid, targets=in_scope):
                    await self.ctx.emit(
                        EventType.KATANA_RESULTS_BATCH,
                        {
                            "program_id": program_id,
                            "results": batch,
                        },
                    )
