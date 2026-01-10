"""ASN Track pipeline nodes"""

from typing import Dict, Any
from uuid import UUID
import asyncio

from api.infrastructure.events.event_types import EventType
from api.application.pipeline.base import PipelineNode
from api.application.services.linkfinder import LinkFinderScanService
from api.application.services.mantra import MantraScanService


class JSFilesDiscoveredNode(PipelineNode):
    """
    Handles JS_FILES_DISCOVERED event.

    Role:
    - Filter JS files by scope
    - Trigger LinkFinder and Mantra scans in parallel
    - Publish GAU_DISCOVERED for LinkFinder URLs (shared event for URL sources)
    - Publish MANTRA_RESULTS_BATCH for secrets

    Event flow:
    IN:  JS_FILES_DISCOVERED
    OUT: GAU_DISCOVERED, MANTRA_RESULTS_BATCH
    """

    event_in = EventType.JS_FILES_DISCOVERED
    event_out = [EventType.GAU_DISCOVERED, EventType.MANTRA_RESULTS_BATCH]

    async def process(self, event: Dict[str, Any]) -> None:
        program_id = UUID(event["program_id"])
        js_files = event["js_files"]

        self.logger.info(
            f"JS files discovered: program={program_id} count={len(js_files)}"
        )

        in_scope, out_of_scope = await self.ctx.scope.filter_urls(
            program_id, js_files
        )

        if out_of_scope:
            self.logger.info(
                f"Filtered out-of-scope JS files: program={program_id} "
                f"in_scope={len(in_scope)} out_of_scope={len(out_of_scope)}"
            )

        if not in_scope:
            self.logger.info(f"No in-scope JS files to scan: program={program_id}")
            return

        async with self.ctx.acquire_scan_slot():
            async with self.ctx.container() as request_container:
                linkfinder_service = await request_container.get(
                    LinkFinderScanService
                )
                mantra_service = await request_container.get(MantraScanService)

                self.logger.info(
                    f"Starting LinkFinder and Mantra scans: "
                    f"program={program_id} files={len(in_scope)}"
                )

                async def run_linkfinder():
                    async for urls in linkfinder_service.execute(
                        program_id=program_id, targets=in_scope
                    ):
                        await self.ctx.emit(
                            EventType.GAU_DISCOVERED,
                            {
                                "program_id": str(program_id),
                                "urls": urls,
                            },
                        )

                async def run_mantra():
                    async for results in mantra_service.execute(
                        program_id=program_id, targets=in_scope
                    ):
                        await self.ctx.emit(
                            EventType.MANTRA_RESULTS_BATCH,
                            {
                                "program_id": str(program_id),
                                "results": results,
                            },
                        )

                await asyncio.gather(
                    run_linkfinder(),
                    run_mantra(),
                    return_exceptions=True,
                )


class CNAMEDiscoveredNode(PipelineNode):
    """
    Handles CNAME_DISCOVERED event.

    Role:
    - Trigger Subjack scan for subdomain takeover detection
    - Publish SUBJACK_RESULTS_BATCH

    Event flow:
    IN:  CNAME_DISCOVERED
    OUT: SUBJACK_RESULTS_BATCH
    """

    event_in = EventType.CNAME_DISCOVERED
    event_out = [EventType.SUBJACK_RESULTS_BATCH]

    async def process(self, event: Dict[str, Any]) -> None:
        program_id = UUID(event["program_id"])
        hosts = event["hosts"]

        self.logger.info(
            f"CNAME hosts discovered, launching Subjack: "
            f"program={program_id} count={len(hosts)}"
        )

        async with self.ctx.acquire_scan_slot():
            async with self.ctx.container() as request_container:
                from api.application.services.subjack import SubjackScanService

                subjack_service = await request_container.get(SubjackScanService)

                self.logger.info(
                    f"Starting Subjack scan: program={program_id} hosts={len(hosts)}"
                )

                async for batch in subjack_service.execute(program_id=program_id, targets=hosts):
                    await self.ctx.emit(
                        EventType.SUBJACK_RESULTS_BATCH,
                        {
                            "program_id": str(program_id),
                            "results": batch,
                        },
                    )


class SubjackResultsNode(PipelineNode):
    """Ingest Subjack subdomain takeover results"""

    event_in = EventType.SUBJACK_RESULTS_BATCH
    event_out = []

    async def process(self, event: Dict[str, Any]) -> None:
        program_id = UUID(event["program_id"])
        results = event["results"]

        self.logger.info(
            f"Ingesting Subjack results: program={program_id} count={len(results)}"
        )

        async with self.ctx.container() as request_container:
            from api.infrastructure.ingestors.subjack_ingestor import (
                SubjackResultIngestor,
            )

            ingestor = await request_container.get(SubjackResultIngestor)
            await ingestor.ingest(program_id, results)


class CIDRDiscoveredNode(PipelineNode):
    """
    Handles CIDR_DISCOVERED event.

    Role in ASN Track:
    - Trigger MapCIDR IP expansion
    - Collect IPs and publish IPS_EXPANDED event

    Event flow:
    IN:  CIDR_DISCOVERED
    OUT: IPS_EXPANDED
    """

    event_in = EventType.CIDR_DISCOVERED
    event_out = [EventType.IPS_EXPANDED]

    async def process(self, event: Dict[str, Any]) -> None:
        program_id = UUID(event["program_id"])
        cidrs = event["cidrs"]

        self.logger.info(
            f"CIDR discovered, triggering MapCIDR: "
            f"program={program_id} cidrs={len(cidrs)}"
        )

        async with self.ctx.container() as request_container:
            from api.application.services.mapcidr import MapCIDRService

            mapcidr_service = await request_container.get(MapCIDRService)

            ips = []
            async for ip in mapcidr_service.expand(program_id=program_id, cidrs=cidrs):
                ips.append(ip)

            if ips:
                await self.ctx.emit(
                    EventType.IPS_EXPANDED,
                    {
                        "program_id": str(program_id),
                        "ips": ips,
                        "source_cidrs": cidrs,
                    },
                )


class IPsExpandedNode(PipelineNode):
    """
    Handles IPS_EXPANDED event from MapCIDR.

    Role in ASN Track:
    - Trigger Naabu port scan, publish NAABU_RESULTS_BATCH
    - Trigger TLSx certificate scan, publish TLSX_RESULTS_BATCH
    - Both run in parallel

    Event flow:
    IN:  IPS_EXPANDED
    OUT: NAABU_RESULTS_BATCH, TLSX_RESULTS_BATCH
    """

    event_in = EventType.IPS_EXPANDED
    event_out = [EventType.NAABU_RESULTS_BATCH, EventType.TLSX_RESULTS_BATCH]

    async def process(self, event: Dict[str, Any]) -> None:
        program_id = UUID(event["program_id"])
        ips = event["ips"]
        source_cidrs = event.get("source_cidrs", [])

        self.logger.info(
            f"IPs expanded, launching ASN Track scans: "
            f"program={program_id} ips={len(ips)} cidrs={len(source_cidrs)}"
        )

        async with self.ctx.acquire_scan_slot():
            async with self.ctx.container() as request_container:
                from api.application.services.naabu import NaabuScanService
                from api.application.services.tlsx import TLSxScanService

                naabu_service = await request_container.get(NaabuScanService)
                tlsx_service = await request_container.get(TLSxScanService)

                self.logger.info(
                    f"Starting parallel Naabu + TLSx scans: "
                    f"program={program_id} ips={len(ips)}"
                )

                async def run_naabu():
                    async for batch_with_meta in naabu_service.execute(program_id=program_id, hosts=ips):
                        await self.ctx.emit(
                            EventType.NAABU_RESULTS_BATCH,
                            {
                                "program_id": str(program_id),
                                **batch_with_meta,
                            },
                        )

                async def run_tlsx():
                    async for batch in tlsx_service.execute_default(program_id=program_id, targets=ips):
                        await self.ctx.emit(
                            EventType.TLSX_RESULTS_BATCH,
                            {
                                "program_id": str(program_id),
                                "results": batch,
                            },
                        )

                await asyncio.gather(
                    run_naabu(),
                    run_tlsx(),
                    return_exceptions=True,
                )

                self.logger.info(
                    f"ASN Track scans completed: program={program_id} ips={len(ips)}"
                )
