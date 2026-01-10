"""DNSx Basic results pipeline node"""

from typing import Dict, Any
from uuid import UUID

from api.infrastructure.events.event_types import EventType
from api.application.pipeline.base import PipelineNode
from api.infrastructure.ingestors.dnsx_ingestor import DNSxResultIngestor


class DNSxBasicResultsNode(PipelineNode):
    """
    Handles DNSX_BASIC_RESULTS_BATCH event.

    Role in DNS Track:
    - Ingest DNSx Basic results
    - Filter out wildcard records
    - Publish non-wildcard hosts for HTTPX

    Event flow:
    IN:  DNSX_BASIC_RESULTS_BATCH
    OUT: DNSX_FILTERED_HOSTS
    """

    event_in = EventType.DNSX_BASIC_RESULTS_BATCH
    event_out = [EventType.DNSX_FILTERED_HOSTS]

    async def process(self, event: Dict[str, Any]) -> None:
        program_id = UUID(event["program_id"])
        results = event["results"]

        self.logger.info(
            f"Processing DNSx Basic results: program={program_id} count={len(results)}"
        )

        async with self.ctx.container() as request_container:
            ingestor = await request_container.get(DNSxResultIngestor)
            await ingestor.ingest(program_id, results)

        non_wildcard_hosts = [
            r["host"]
            for r in results
            if not r.get("wildcard", False) and r.get("host")
        ]

        wildcard_count = len(results) - len(non_wildcard_hosts)

        self.logger.info(
            f"DNSx Basic filtering: program={program_id} "
            f"total={len(results)} wildcard={wildcard_count} real={len(non_wildcard_hosts)}"
        )

        if non_wildcard_hosts:
            await self.ctx.emit(
                EventType.DNSX_FILTERED_HOSTS,
                {"program_id": str(program_id), "hosts": non_wildcard_hosts},
            )
