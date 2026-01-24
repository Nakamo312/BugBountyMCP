"""Service for infrastructure graph visualization"""

import logging
from typing import Dict, List
from uuid import UUID

from api.application.dto.infrastructure import (
    GraphNodeDTO,
    GraphEdgeDTO,
    InfrastructureGraphDTO,
)
from api.infrastructure.unit_of_work.interfaces.infrastructure import InfrastructureUnitOfWork

logger = logging.getLogger(__name__)


class InfrastructureService:
    """Service for building infrastructure graph"""

    def __init__(self, uow: InfrastructureUnitOfWork):
        self.uow = uow

    async def get_infrastructure_graph(
        self,
        program_id: UUID,
    ) -> InfrastructureGraphDTO:
        """Build infrastructure graph for a program"""
        async with self.uow as uow:
            nodes: List[GraphNodeDTO] = []
            edges: List[GraphEdgeDTO] = []
            stats: Dict[str, int] = {}

            asns = await uow.asns.find_many(filters={"program_id": program_id}, limit=10000)
            stats["asn_count"] = len(asns)
            for asn in asns:
                nodes.append(GraphNodeDTO(
                    id=f"asn-{asn.id}",
                    type="asn",
                    label=f"AS{asn.asn_number}",
                    data={
                        "asn_number": asn.asn_number,
                        "organization": asn.organization_name,
                        "country": asn.country_code,
                    }
                ))

            cidrs = await uow.cidrs.find_many(filters={"program_id": program_id}, limit=10000)
            stats["cidr_count"] = len(cidrs)
            for cidr in cidrs:
                nodes.append(GraphNodeDTO(
                    id=f"cidr-{cidr.id}",
                    type="cidr",
                    label=cidr.cidr,
                    data={
                        "ip_count": cidr.ip_count,
                        "in_scope": cidr.in_scope,
                    }
                ))
                if cidr.asn_id:
                    edges.append(GraphEdgeDTO(
                        source=f"asn-{cidr.asn_id}",
                        target=f"cidr-{cidr.id}",
                        type="contains"
                    ))

            ips = await uow.ips.find_many(filters={"program_id": program_id}, limit=10000)
            stats["ip_count"] = len(ips)
            for ip in ips:
                nodes.append(GraphNodeDTO(
                    id=f"ip-{ip.id}",
                    type="ip",
                    label=ip.address,
                    data={
                        "in_scope": ip.in_scope,
                    }
                ))

            services = await uow.services.find_by_program_id(program_id)
            stats["service_count"] = len(services)
            for svc in services:
                nodes.append(GraphNodeDTO(
                    id=f"svc-{svc.id}",
                    type="service",
                    label=f"{svc.scheme}:{svc.port}",
                    data={
                        "scheme": svc.scheme,
                        "port": svc.port,
                        "technologies": svc.technologies or {},
                    }
                ))
                edges.append(GraphEdgeDTO(
                    source=f"ip-{svc.ip_id}",
                    target=f"svc-{svc.id}",
                    type="runs"
                ))

            hosts = await uow.hosts.find_many(filters={"program_id": program_id}, limit=10000)
            stats["host_count"] = len(hosts)
            for host in hosts:
                nodes.append(GraphNodeDTO(
                    id=f"host-{host.id}",
                    type="host",
                    label=host.host,
                    data={
                        "in_scope": host.in_scope,
                        "cname": host.cname or [],
                    }
                ))

            host_ips = await uow.host_ips.find_by_program_id(program_id)
            for hip in host_ips:
                edges.append(GraphEdgeDTO(
                    source=f"host-{hip.host_id}",
                    target=f"ip-{hip.ip_id}",
                    type="resolves_to"
                ))

            return InfrastructureGraphDTO(
                nodes=nodes,
                edges=edges,
                stats=stats
            )
