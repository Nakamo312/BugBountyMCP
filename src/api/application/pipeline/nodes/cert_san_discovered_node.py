"""Certificate SAN discovered pipeline node"""

from typing import Dict, Any
from uuid import UUID

from api.infrastructure.events.event_types import EventType
from api.application.pipeline.base import PipelineNode


class CertSANDiscoveredNode(PipelineNode):
    """
    Handles CERT_SAN_DISCOVERED event from TLSx certificate scans.

    Role:
    - Receives domains extracted from TLS certificates
    - Filters by scope
    - Publishes as SUBDOMAIN_DISCOVERED for DNS Track processing

    Event flow:
    IN:  CERT_SAN_DISCOVERED
    OUT: SUBDOMAIN_DISCOVERED
    """

    event_in = EventType.CERT_SAN_DISCOVERED
    event_out = [EventType.SUBDOMAIN_DISCOVERED]

    async def process(self, event: Dict[str, Any]) -> None:
        program_id = UUID(event["program_id"])
        domains = event["domains"]

        self.logger.info(
            f"Certificate domains discovered: program={program_id} count={len(domains)}"
        )

        in_scope, out_of_scope = await self.ctx.scope.filter_domains(
            program_id, domains
        )

        if out_of_scope:
            self.logger.info(
                f"Filtered out-of-scope cert domains: program={program_id} "
                f"in_scope={len(in_scope)} out_of_scope={len(out_of_scope)}"
            )

        if not in_scope:
            self.logger.info(f"No in-scope cert domains: program={program_id}")
            return

        self.logger.info(
            f"Publishing cert domains as subdomains: "
            f"program={program_id} count={len(in_scope)}"
        )

        await self.ctx.emit(
            EventType.SUBDOMAIN_DISCOVERED,
            {
                "program_id": str(program_id),
                "subdomains": in_scope,
            },
        )
