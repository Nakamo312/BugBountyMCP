"""Pure infrastructure graph projection builder.

This module keeps read-model assembly out of ``InfrastructureService``.  The
service owns data access; this builder owns DTO shape and relationship derivation.
"""

from __future__ import annotations

from dataclasses import dataclass
import ipaddress
from typing import Iterable
from uuid import UUID

from api.application.dto.infrastructure import (
    GraphEdgeDTO,
    GraphNodeDTO,
    InfrastructureGraphDTO,
)
from api.domain.models import (
    ASNModel,
    CIDRModel,
    HostIPModel,
    HostModel,
    IPAddressModel,
    ServiceModel,
)


@dataclass(frozen=True)
class _ParsedCidr:
    cidr_id: UUID
    network: ipaddress.IPv4Network | ipaddress.IPv6Network


class CidrContainmentIndex:
    """Parsed CIDR lookup used by the infrastructure graph projection.

    This is still an in-process read-model helper, not a database projection.
    It removes the old API hot path where every IP/CIDR comparison reparsed both
    strings and made the complexity harder to isolate.
    """

    def __init__(self, networks: Iterable[_ParsedCidr]):
        ipv4: list[_ParsedCidr] = []
        ipv6: list[_ParsedCidr] = []
        for item in networks:
            if item.network.version == 4:
                ipv4.append(item)
            else:
                ipv6.append(item)
        self._by_version = {4: tuple(ipv4), 6: tuple(ipv6)}

    @classmethod
    def from_cidrs(cls, cidrs: Iterable[CIDRModel]) -> "CidrContainmentIndex":
        parsed: list[_ParsedCidr] = []
        for cidr in cidrs:
            try:
                network = ipaddress.ip_network(cidr.cidr, strict=False)
            except ValueError:
                continue
            parsed.append(_ParsedCidr(cidr_id=cidr.id, network=network))
        return cls(parsed)

    def first_container_for(self, ip_str: str) -> UUID | None:
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            return None

        for candidate in self._by_version[ip.version]:
            if ip in candidate.network:
                return candidate.cidr_id
        return None


def ip_in_cidr(ip_str: str, cidr_str: str) -> bool:
    """Return whether an IP address belongs to a CIDR block."""
    try:
        ip = ipaddress.ip_address(ip_str)
        network = ipaddress.ip_network(cidr_str, strict=False)
        return ip in network
    except ValueError:
        return False


def build_infrastructure_graph(
    *,
    asns: list[ASNModel],
    cidrs: list[CIDRModel],
    ips: list[IPAddressModel],
    hosts: list[HostModel],
    host_ips: list[HostIPModel],
    services: list[ServiceModel],
) -> InfrastructureGraphDTO:
    """Build the infrastructure graph DTO from already-loaded records."""
    nodes: list[GraphNodeDTO] = []
    edges: list[GraphEdgeDTO] = []

    nodes.extend(_asn_nodes(asns))
    cidr_nodes, cidr_edges = _cidr_projection(cidrs)
    nodes.extend(cidr_nodes)
    edges.extend(cidr_edges)

    ip_nodes, ip_edges = _ip_projection(ips, CidrContainmentIndex.from_cidrs(cidrs))
    nodes.extend(ip_nodes)
    edges.extend(ip_edges)

    nodes.extend(_host_nodes(hosts))
    host_ip_edges, ip_to_hosts = _host_ip_projection(host_ips)
    edges.extend(host_ip_edges)

    service_nodes, service_edges = _service_projection(services, ip_to_hosts)
    nodes.extend(service_nodes)
    edges.extend(service_edges)

    return InfrastructureGraphDTO(
        nodes=nodes,
        edges=edges,
        stats={
            "asn_count": len(asns),
            "cidr_count": len(cidrs),
            "ip_count": len(ips),
            "host_count": len(hosts),
            "service_count": len(services),
        },
    )


def _asn_nodes(asns: list[ASNModel]) -> list[GraphNodeDTO]:
    return [
        GraphNodeDTO(
            id=f"asn-{asn.id}",
            type="asn",
            label=f"AS{asn.asn_number}",
            data={
                "asn_number": asn.asn_number,
                "organization": asn.organization_name,
                "country": asn.country_code,
            },
        )
        for asn in asns
    ]


def _cidr_projection(cidrs: list[CIDRModel]) -> tuple[list[GraphNodeDTO], list[GraphEdgeDTO]]:
    nodes: list[GraphNodeDTO] = []
    edges: list[GraphEdgeDTO] = []

    for cidr in cidrs:
        nodes.append(
            GraphNodeDTO(
                id=f"cidr-{cidr.id}",
                type="cidr",
                label=cidr.cidr,
                data={
                    "ip_count": cidr.ip_count,
                    "in_scope": cidr.in_scope,
                },
            )
        )
        if cidr.asn_id:
            edges.append(
                GraphEdgeDTO(
                    source=f"asn-{cidr.asn_id}",
                    target=f"cidr-{cidr.id}",
                    type="contains",
                )
            )

    return nodes, edges


def _ip_projection(
    ips: list[IPAddressModel],
    cidrs: CidrContainmentIndex,
) -> tuple[list[GraphNodeDTO], list[GraphEdgeDTO]]:
    nodes: list[GraphNodeDTO] = []
    edges: list[GraphEdgeDTO] = []

    for ip in ips:
        nodes.append(
            GraphNodeDTO(
                id=f"ip-{ip.id}",
                type="ip",
                label=ip.address,
                data={"in_scope": ip.in_scope},
            )
        )
        if cidr_id := cidrs.first_container_for(ip.address):
            edges.append(
                GraphEdgeDTO(
                    source=f"cidr-{cidr_id}",
                    target=f"ip-{ip.id}",
                    type="contains",
                )
            )

    return nodes, edges


def _host_nodes(hosts: list[HostModel]) -> list[GraphNodeDTO]:
    return [
        GraphNodeDTO(
            id=f"host-{host.id}",
            type="host",
            label=host.host,
            data={
                "in_scope": host.in_scope,
                "cname": host.cname or [],
            },
        )
        for host in hosts
    ]


def _host_ip_projection(
    host_ips: list[HostIPModel],
) -> tuple[list[GraphEdgeDTO], dict[UUID, list[UUID]]]:
    edges: list[GraphEdgeDTO] = []
    ip_to_hosts: dict[UUID, list[UUID]] = {}

    for host_ip in host_ips:
        edges.append(
            GraphEdgeDTO(
                source=f"ip-{host_ip.ip_id}",
                target=f"host-{host_ip.host_id}",
                type="resolves_to",
            )
        )
        ip_to_hosts.setdefault(host_ip.ip_id, []).append(host_ip.host_id)

    return edges, ip_to_hosts


def _service_projection(
    services: list[ServiceModel],
    ip_to_hosts: dict[UUID, list[UUID]],
) -> tuple[list[GraphNodeDTO], list[GraphEdgeDTO]]:
    nodes: list[GraphNodeDTO] = []
    edges: list[GraphEdgeDTO] = []

    for service in services:
        nodes.append(
            GraphNodeDTO(
                id=f"svc-{service.id}",
                type="service",
                label=f"{service.scheme}:{service.port}",
                data={
                    "scheme": service.scheme,
                    "port": service.port,
                    "technologies": service.technologies or {},
                },
            )
        )
        for host_id in ip_to_hosts.get(service.ip_id, ()):  # noqa: SIM118 - accepts list or tuple
            edges.append(
                GraphEdgeDTO(
                    source=f"host-{host_id}",
                    target=f"svc-{service.id}",
                    type="runs",
                )
            )

    return nodes, edges
