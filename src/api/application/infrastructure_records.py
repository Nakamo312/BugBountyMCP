"""Application boundary for infrastructure graph source records."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from api.domain.models import (
    ASNModel,
    CIDRModel,
    HostIPModel,
    HostModel,
    IPAddressModel,
    ServiceModel,
)


@dataclass(frozen=True)
class InfrastructureGraphRecords:
    asns: list[ASNModel]
    cidrs: list[CIDRModel]
    ips: list[IPAddressModel]
    hosts: list[HostModel]
    host_ips: list[HostIPModel]
    services: list[ServiceModel]


class InfrastructureGraphReader(Protocol):
    async def get_graph_records(self, program_id: UUID) -> InfrastructureGraphRecords:
        raise NotImplementedError
