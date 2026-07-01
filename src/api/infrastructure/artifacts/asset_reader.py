"""Host, IP, service, and DNS artifact queries."""
from __future__ import annotations

import uuid

from sqlalchemy import String, cast, or_, select

from api.application.artifact_contracts import (
    DNSRecordArtifact,
    HostArtifact,
    IPArtifact,
    ServiceArtifact,
)
from api.infrastructure.adapters.orm import (
    dns_records,
    host_ips,
    hosts,
    ip_addresses,
    services,
)
from api.infrastructure.artifacts.common import ArtifactQueryExecutor


class AssetArtifactReader:
    """Read inventory artifacts that describe infrastructure assets."""

    def __init__(self, executor: ArtifactQueryExecutor):
        self.executor = executor

    async def list_hosts(
        self,
        program_id: uuid.UUID,
        q: str | None = None,
        in_scope: bool | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[HostArtifact]:
        query = select(hosts).where(hosts.c.program_id == program_id)
        if q:
            query = query.where(hosts.c.host.ilike(f"%{q}%"))
        if in_scope is not None:
            query = query.where(hosts.c.in_scope == in_scope)
        rows = await self.executor.fetch_all(query.order_by(hosts.c.host), limit, offset)
        return [HostArtifact.model_validate(row) for row in rows]

    async def list_ips(
        self,
        program_id: uuid.UUID,
        q: str | None = None,
        in_scope: bool | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[IPArtifact]:
        query = select(ip_addresses).where(ip_addresses.c.program_id == program_id)
        if q:
            query = query.where(ip_addresses.c.address.ilike(f"%{q}%"))
        if in_scope is not None:
            query = query.where(ip_addresses.c.in_scope == in_scope)
        rows = await self.executor.fetch_all(query.order_by(ip_addresses.c.address), limit, offset)
        return [IPArtifact.model_validate(row) for row in rows]

    async def list_services(
        self,
        program_id: uuid.UUID,
        host_id: uuid.UUID | None = None,
        port: int | None = None,
        scheme: str | None = None,
        tech: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[ServiceArtifact]:
        query = (
            select(
                services.c.id,
                services.c.ip_id,
                ip_addresses.c.address,
                services.c.scheme,
                services.c.port,
                services.c.technologies,
                services.c.favicon_hash,
                services.c.websocket,
            )
            .select_from(services.join(ip_addresses, services.c.ip_id == ip_addresses.c.id))
            .where(ip_addresses.c.program_id == program_id)
        )
        if host_id:
            query = query.select_from(
                services
                .join(ip_addresses, services.c.ip_id == ip_addresses.c.id)
                .join(host_ips, host_ips.c.ip_id == ip_addresses.c.id)
            ).where(host_ips.c.host_id == host_id)
        if port is not None:
            query = query.where(services.c.port == port)
        if scheme:
            query = query.where(services.c.scheme == scheme)
        if tech:
            query = query.where(cast(services.c.technologies, String).ilike(f"%{tech}%"))
        rows = await self.executor.fetch_all(
            query.order_by(ip_addresses.c.address, services.c.port),
            limit,
            offset,
        )
        return [ServiceArtifact.model_validate(row) for row in rows]

    async def list_dns_records(
        self,
        program_id: uuid.UUID,
        host_id: uuid.UUID | None = None,
        record_type: str | None = None,
        q: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[DNSRecordArtifact]:
        query = (
            select(
                dns_records.c.id,
                dns_records.c.host_id,
                hosts.c.host,
                dns_records.c.record_type,
                dns_records.c.value,
                dns_records.c.ttl,
                dns_records.c.priority,
                dns_records.c.is_wildcard,
            )
            .select_from(dns_records.join(hosts, dns_records.c.host_id == hosts.c.id))
            .where(hosts.c.program_id == program_id)
        )
        if host_id:
            query = query.where(dns_records.c.host_id == host_id)
        if record_type:
            query = query.where(dns_records.c.record_type == record_type.upper())
        if q:
            query = query.where(or_(hosts.c.host.ilike(f"%{q}%"), dns_records.c.value.ilike(f"%{q}%")))
        rows = await self.executor.fetch_all(
            query.order_by(hosts.c.host, dns_records.c.record_type),
            limit,
            offset,
        )
        return [DNSRecordArtifact.model_validate(row) for row in rows]
