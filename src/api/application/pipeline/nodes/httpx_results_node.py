"""HTTPX results pipeline node"""

from typing import Dict, Any
from uuid import UUID

from api.infrastructure.events.event_types import EventType
from api.application.pipeline.base import PipelineNode
from api.infrastructure.ingestors.httpx_ingestor import HTTPXResultIngestor


class HTTPXResultsNode(PipelineNode):
    """
    Handles SCAN_RESULTS_BATCH (HTTPX results).

    Role in DNS Track:
    - Ingest HTTPX results
    - Publish newly discovered hosts (for Katana crawling)
    - Publish live hosts (for DNSx Deep scan)
    - Publish discovered JS files (for LinkFinder/Mantra analysis)

    Event flow:
    IN:  SCAN_RESULTS_BATCH
    OUT: HOST_DISCOVERED, JS_FILES_DISCOVERED
    """

    event_in = EventType.SCAN_RESULTS_BATCH
    event_out = [EventType.HOST_DISCOVERED, EventType.JS_FILES_DISCOVERED]

    async def process(self, event: Dict[str, Any]) -> None:
        program_id = UUID(event["program_id"])
        results = event["results"]

        self.logger.info(
            f"Ingesting HTTPX results: program={program_id} count={len(results)}"
        )

        async with self.ctx.container() as request_container:
            ingestor = await request_container.get(HTTPXResultIngestor)
            await ingestor.ingest(program_id, results)

            for batch in ingestor.discovered_hosts_batches:
                self.logger.info(
                    f"Publishing newly discovered hosts batch for Katana: "
                    f"program={program_id} count={len(batch)}"
                )

                await self.ctx.emit(
                    EventType.HOST_DISCOVERED,
                    {
                        "program_id": str(program_id),
                        "hosts": batch,
                    },
                )

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

        live_hosts = list(
            {
                r.get("host")
                for r in results
                if r.get("host") and r.get("status_code")
            }
        )

        if live_hosts:
            self.logger.info(
                f"Publishing live hosts for DNSx Deep: "
                f"program={program_id} count={len(live_hosts)}"
            )

            await self.ctx.emit(
                EventType.HOST_DISCOVERED,
                {
                    "program_id": str(program_id),
                    "hosts": live_hosts,
                    "source": "httpx_for_dnsx_deep",
                },
            )
