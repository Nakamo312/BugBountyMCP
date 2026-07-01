"""Repository-backed infrastructure graph record reader."""
from __future__ import annotations

from uuid import UUID

from api.application.infrastructure_records import (
    InfrastructureGraphReader,
    InfrastructureGraphRecords,
)
from api.infrastructure.unit_of_work.interfaces.infrastructure import InfrastructureUnitOfWork

_GRAPH_ROWS_LIMIT = 10000


class RepositoryInfrastructureGraphReader(InfrastructureGraphReader):
    def __init__(self, uow: InfrastructureUnitOfWork) -> None:
        self._uow = uow

    async def get_graph_records(self, program_id: UUID) -> InfrastructureGraphRecords:
        filters = {"program_id": program_id}
        async with self._uow as uow:
            return InfrastructureGraphRecords(
                asns=await uow.asns.find_many(filters=filters, limit=_GRAPH_ROWS_LIMIT),
                cidrs=await uow.cidrs.find_many(filters=filters, limit=_GRAPH_ROWS_LIMIT),
                ips=await uow.ips.find_many(filters=filters, limit=_GRAPH_ROWS_LIMIT),
                hosts=await uow.hosts.find_many(filters=filters, limit=_GRAPH_ROWS_LIMIT),
                host_ips=await uow.host_ips.find_by_program_id(program_id),
                services=await uow.services.find_by_program_id(program_id),
            )
