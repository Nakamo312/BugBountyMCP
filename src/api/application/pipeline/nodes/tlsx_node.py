"""TLSx certificate scan pipeline node"""

from typing import Dict, Any
from uuid import UUID

from api.infrastructure.events.event_types import EventType
from api.application.pipeline.base import PipelineNode


class TLSxCertNode(PipelineNode):
    """
    TLSx certificate scan results processor.

    Role in architecture:
    - Extract domains from certificates (SAN/CN) as tokens
    - Publish CERT_SAN_DISCOVERED for token collection
    - Does NOT filter IPs (ASN Track independence)
    - Does NOT trigger HTTPx (handled by PortsDiscoveredNode)

    Event flow:
    IN:  TLSX_RESULTS_BATCH
    OUT: CERT_SAN_DISCOVERED
    """

    event_in = EventType.TLSX_RESULTS_BATCH
    event_out = [EventType.CERT_SAN_DISCOVERED]

    async def process(self, event: Dict[str, Any]) -> None:
        program_id = event["program_id"]
        results = event["results"]

        self.logger.info(
            f"Processing TLSx results: program={program_id} count={len(results)}"
        )

        all_domains = set()

        for result in results:
            subject_an = result.get("subject_an", [])
            if subject_an:
                for domain in subject_an:
                    if domain and isinstance(domain, str):
                        all_domains.add(domain)

            subject_cn = result.get("subject_cn")
            if subject_cn and isinstance(subject_cn, str):
                all_domains.add(subject_cn)

        if all_domains:
            self.logger.info(
                f"Extracted {len(all_domains)} domains from certificates: "
                f"program={program_id}"
            )

            await self.ctx.emit(
                EventType.CERT_SAN_DISCOVERED,
                {
                    "program_id": program_id,
                    "domains": list(all_domains),
                },
            )
        else:
            self.logger.debug(
                f"No domains found in TLSx results: program={program_id}"
            )
