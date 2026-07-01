"""Service for infrastructure graph visualization."""

from uuid import UUID

from api.application.dto.infrastructure import InfrastructureGraphDTO
from api.application.infrastructure_graph_projection import (
    build_infrastructure_graph,
    ip_in_cidr,
)
from api.application.infrastructure_records import InfrastructureGraphReader


class InfrastructureService:
    """Load infrastructure graph source records and assemble the DTO."""

    def __init__(self, reader: InfrastructureGraphReader):
        self._reader = reader

    async def get_infrastructure_graph(
        self,
        program_id: UUID,
    ) -> InfrastructureGraphDTO:
        """Build infrastructure graph for a program."""
        records = await self._reader.get_graph_records(program_id)
        return build_infrastructure_graph(
            asns=records.asns,
            cidrs=records.cidrs,
            ips=records.ips,
            hosts=records.hosts,
            host_ips=records.host_ips,
            services=records.services,
        )


__all__ = ["InfrastructureService", "ip_in_cidr"]
