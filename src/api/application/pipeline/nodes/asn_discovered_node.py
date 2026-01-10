"""ASN discovered node - placeholder for future ASN queries"""

from typing import Dict, Any
from uuid import UUID

from api.infrastructure.events.event_types import EventType
from api.application.pipeline.base import PipelineNode


class ASNDiscoveredNode(PipelineNode):
    """
    Handles ASN_DISCOVERED event.

    Currently just logs - placeholder for future ASN-based queries.
    Could trigger additional ASN enumeration, WHOIS queries, etc.

    Event flow:
    IN:  ASN_DISCOVERED
    OUT: (none - future implementation)
    """

    event_in = EventType.ASN_DISCOVERED
    event_out = []

    async def process(self, event: Dict[str, Any]) -> None:
        program_id = UUID(event["program_id"])
        asns = event["asns"]

        self.logger.info(
            f"ASN discovered: program={program_id} count={len(asns)}"
        )

        # Future: trigger additional ASN queries, WHOIS, etc.
