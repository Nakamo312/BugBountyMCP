"""Service for infrastructure graph visualization."""

from uuid import UUID

from api.application.dto.infrastructure import InfrastructureGraphDTO
from api.application.infrastructure_graph_projection import (
    build_infrastructure_graph,
    ip_in_cidr,
)
from api.infrastructure.unit_of_work.interfaces.infrastructure import InfrastructureUnitOfWork


class InfrastructureService:
    """Load infrastructure records and delegate read-model assembly."""

    def __init__(self, uow: InfrastructureUnitOfWork):
        self.uow = uow

    async def get_infrastructure_graph(
        self,
        program_id: UUID,
    ) -> InfrastructureGraphDTO:
        """Build infrastructure graph for a program."""
        async with self.uow as uow:
            asns = await uow.asns.find_many(filters={"program_id": program_id}, limit=10000)
            cidrs = await uow.cidrs.find_many(filters={"program_id": program_id}, limit=10000)
            ips = await uow.ips.find_many(filters={"program_id": program_id}, limit=10000)
            hosts = await uow.hosts.find_many(filters={"program_id": program_id}, limit=10000)
            host_ips = await uow.host_ips.find_by_program_id(program_id)
            services = await uow.services.find_by_program_id(program_id)

        return build_infrastructure_graph(
            asns=asns,
            cidrs=cidrs,
            ips=ips,
            hosts=hosts,
            host_ips=host_ips,
            services=services,
        )


__all__ = ["InfrastructureService", "ip_in_cidr"]
