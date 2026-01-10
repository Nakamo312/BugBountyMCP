"""Simple ingestor nodes for results that only need storage"""

from typing import Dict, Any
from uuid import UUID

from api.infrastructure.events.event_types import EventType
from api.application.pipeline.base import PipelineNode
from api.infrastructure.ingestors.katana_ingestor import KatanaResultIngestor
from api.infrastructure.ingestors.mantra_ingestor import MantraResultIngestor
from api.infrastructure.ingestors.ffuf_ingestor import FFUFResultIngestor
from api.infrastructure.ingestors.dnsx_ingestor import DNSxResultIngestor
from api.infrastructure.ingestors.asnmap_ingestor import ASNMapResultIngestor


class KatanaResultsNode(PipelineNode):
    """
    Ingest Katana crawl results and publish discovered JS files.

    Event flow:
    IN:  KATANA_RESULTS_BATCH
    OUT: JS_FILES_DISCOVERED
    """

    event_in = EventType.KATANA_RESULTS_BATCH
    event_out = [EventType.JS_FILES_DISCOVERED]

    async def process(self, event: Dict[str, Any]) -> None:
        program_id = UUID(event["program_id"])
        results = event["results"]

        self.logger.info(
            f"Ingesting Katana results: program={program_id} count={len(results)}"
        )

        async with self.ctx.container() as request_container:
            ingestor = await request_container.get(KatanaResultIngestor)
            await ingestor.ingest(program_id, results)

            for batch in ingestor.discovered_js_files_batches:
                self.logger.info(
                    f"Publishing JS files batch for LinkFinder: "
                    f"program={program_id} count={len(batch)}"
                )

                await self.ctx.emit(
                    EventType.JS_FILES_DISCOVERED,
                    {
                        "program_id": str(program_id),
                        "js_files": batch,
                    },
                )


class MantraResultsNode(PipelineNode):
    """Ingest Mantra JS analysis results"""

    event_in = EventType.MANTRA_RESULTS_BATCH
    event_out = []

    async def process(self, event: Dict[str, Any]) -> None:
        program_id = UUID(event["program_id"])
        results = event["results"]

        self.logger.info(
            f"Ingesting Mantra results: program={program_id} count={len(results)}"
        )

        async with self.ctx.container() as request_container:
            ingestor = await request_container.get(MantraResultIngestor)
            await ingestor.ingest(program_id, results)


class FFUFResultsNode(PipelineNode):
    """Ingest FFUF fuzzing results"""

    event_in = EventType.FFUF_RESULTS_BATCH
    event_out = []

    async def process(self, event: Dict[str, Any]) -> None:
        program_id = UUID(event["program_id"])
        results = event["results"]

        self.logger.info(
            f"Ingesting FFUF results: program={program_id} count={len(results)}"
        )

        async with self.ctx.container() as request_container:
            ingestor = await request_container.get(FFUFResultIngestor)
            await ingestor.ingest(program_id, results)


class DNSxDeepResultsNode(PipelineNode):
    """
    Ingest DNSx Deep results and publish CNAME records for Subjack.

    Event flow:
    IN:  DNSX_DEEP_RESULTS_BATCH
    OUT: CNAME_DISCOVERED
    """

    event_in = EventType.DNSX_DEEP_RESULTS_BATCH
    event_out = [EventType.CNAME_DISCOVERED]

    async def process(self, event: Dict[str, Any]) -> None:
        program_id = UUID(event["program_id"])
        results = event["results"]

        self.logger.info(
            f"Ingesting DNSx Deep results: program={program_id} count={len(results)}"
        )

        async with self.ctx.container() as request_container:
            ingestor = await request_container.get(DNSxResultIngestor)
            await ingestor.ingest(program_id, results)

        cname_hosts = []
        for result in results:
            if result.get("cname") and not result.get("wildcard", False):
                host = result.get("host")
                if host:
                    cname_hosts.append(host)

        if cname_hosts:
            self.logger.info(
                f"Publishing CNAME hosts for Subjack: "
                f"program={program_id} count={len(cname_hosts)}"
            )

            await self.ctx.emit(
                EventType.CNAME_DISCOVERED,
                {"program_id": str(program_id), "hosts": cname_hosts},
            )


class DNSxPTRResultsNode(PipelineNode):
    """
    Ingest DNSx PTR results and publish discovered hosts.

    Event flow:
    IN:  DNSX_PTR_RESULTS_BATCH
    OUT: SUBDOMAIN_DISCOVERED
    """

    event_in = EventType.DNSX_PTR_RESULTS_BATCH
    event_out = [EventType.SUBDOMAIN_DISCOVERED]

    async def process(self, event: Dict[str, Any]) -> None:
        program_id = UUID(event["program_id"])
        results = event["results"]

        self.logger.info(
            f"Ingesting DNSx PTR results: program={program_id} count={len(results)}"
        )

        async with self.ctx.container() as request_container:
            ingestor = await request_container.get(DNSxResultIngestor)
            await ingestor.ingest(program_id, results)

        discovered_hosts = []
        for result in results:
            ptr_records = result.get("ptr", [])
            for ptr in ptr_records:
                if ptr and ptr not in discovered_hosts:
                    discovered_hosts.append(ptr)

        if discovered_hosts:
            self.logger.info(
                f"Publishing PTR-discovered hosts: "
                f"program={program_id} count={len(discovered_hosts)}"
            )

            await self.ctx.emit(
                EventType.SUBDOMAIN_DISCOVERED,
                {"program_id": str(program_id), "subdomains": discovered_hosts},
            )


class ASNMapResultsNode(PipelineNode):
    """
    Ingest ASNMap results and publish discovered ASNs/CIDRs.

    Event flow:
    IN:  ASNMAP_RESULTS_BATCH
    OUT: ASN_DISCOVERED, CIDR_DISCOVERED
    """

    event_in = EventType.ASNMAP_RESULTS_BATCH
    event_out = [EventType.ASN_DISCOVERED, EventType.CIDR_DISCOVERED]

    async def process(self, event: Dict[str, Any]) -> None:
        program_id = UUID(event["program_id"])
        results = event["results"]

        self.logger.info(
            f"Ingesting ASNMap results: program={program_id} count={len(results)}"
        )

        async with self.ctx.container() as request_container:
            ingestor = await request_container.get(ASNMapResultIngestor)
            await ingestor.ingest(program_id, results)

            if ingestor.discovered_asns:
                self.logger.info(
                    f"Publishing ASN discovered: program={program_id} "
                    f"count={len(ingestor.discovered_asns)}"
                )
                await self.ctx.emit(
                    EventType.ASN_DISCOVERED,
                    {
                        "program_id": str(program_id),
                        "asns": list(ingestor.discovered_asns),
                    },
                )

            if ingestor.discovered_cidrs:
                self.logger.info(
                    f"Publishing CIDR discovered: program={program_id} "
                    f"count={len(ingestor.discovered_cidrs)}"
                )
                await self.ctx.emit(
                    EventType.CIDR_DISCOVERED,
                    {
                        "program_id": str(program_id),
                        "cidrs": list(ingestor.discovered_cidrs),
                    },
                )
