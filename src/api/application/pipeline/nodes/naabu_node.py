"""Naabu port scan pipeline node"""

from typing import Dict, Any
from uuid import UUID

from api.infrastructure.events.event_types import EventType
from api.application.pipeline.base import PipelineNode


class NaabuPortsNode(PipelineNode):
    """
    Naabu port scan results processor.

    Role in architecture:
    - Acts as service filter (identifies live IP,PORT pairs)
    - Stores results for historical tracking
    - Publishes PORTS_DISCOVERED for HTTPx baseline scan
    - Critical for ASN Track pipeline

    Event flow:
    IN:  NAABU_RESULTS_BATCH
    OUT: PORTS_DISCOVERED
    """

    event_in = EventType.NAABU_RESULTS_BATCH
    event_out = [EventType.PORTS_DISCOVERED]

    async def process(self, event: Dict[str, Any]) -> None:
        program_id = UUID(event["program_id"])
        results = event["results"]
        scan_mode = event.get("scan_mode", "active")

        self.logger.info(
            f"Processing Naabu results: program={program_id} "
            f"count={len(results)} mode={scan_mode}"
        )

        async with self.ctx.container() as request_container:
            from api.infrastructure.ingestors.naabu_ingestor import NaabuResultIngestor

            ingestor = await request_container.get(NaabuResultIngestor)
            await ingestor.ingest(results, program_id)

        self.logger.info(
            f"Naabu results ingested: program={program_id} count={len(results)}"
        )

        if results:
            await self.ctx.emit(
                EventType.PORTS_DISCOVERED,
                {
                    "program_id": str(program_id),
                    "ports": results,
                },
            )

            self.logger.info(
                f"Published PORTS_DISCOVERED: program={program_id} "
                f"ports={len(results)}"
            )
