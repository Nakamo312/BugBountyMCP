"""Ports discovered pipeline node - triggers HTTPx baseline scan"""

from typing import Dict, Any
from uuid import UUID

from api.infrastructure.events.event_types import EventType
from api.application.pipeline.base import PipelineNode
from api.application.services.httpx import HTTPXScanService


class PortsDiscoveredNode(PipelineNode):
    """
    Handles PORTS_DISCOVERED event from Naabu.

    Role in architecture:
    - Triggers HTTPx baseline scan on (IP,PORT) pairs
    - Publishes HTTPX results as SCAN_RESULTS_BATCH events
    - No Host header - raw HTTP infrastructure probing
    - First HTTP contact in ASN Track
    - Results stored for VHOST fuzzing correlation

    Event flow:
    IN:  PORTS_DISCOVERED
    OUT: SCAN_RESULTS_BATCH
    """

    event_in = EventType.PORTS_DISCOVERED
    event_out = [EventType.SCAN_RESULTS_BATCH]

    async def process(self, event: Dict[str, Any]) -> None:
        program_id = UUID(event["program_id"])
        ports_data = event["ports"]

        self.logger.info(
            f"Ports discovered, launching HTTPx baseline: "
            f"program={program_id} ports={len(ports_data)}"
        )

        ip_port_pairs = []
        for result in ports_data:
            ip = result.get("ip") or result.get("host")
            port = result.get("port")
            if ip and port:
                ip_port_pairs.append(f"{ip}:{port}")

        if not ip_port_pairs:
            self.logger.warning(
                f"No valid IP:PORT pairs in PORTS_DISCOVERED: program={program_id}"
            )
            return

        async with self.ctx.acquire_scan_slot():
            async with self.ctx.container() as request_container:
                httpx_service = await request_container.get(HTTPXScanService)

                self.logger.info(
                    f"Starting HTTPx baseline scan: "
                    f"program={program_id} targets={len(ip_port_pairs)}"
                )

                async for batch in httpx_service.execute(
                    program_id=program_id, targets=ip_port_pairs
                ):
                    await self.ctx.emit(
                        EventType.SCAN_RESULTS_BATCH,
                        {
                            "program_id": str(program_id),
                            "results": batch,
                        },
                    )

                self.logger.info(
                    f"HTTPx baseline scan completed: "
                    f"program={program_id} targets={len(ip_port_pairs)}"
                )
