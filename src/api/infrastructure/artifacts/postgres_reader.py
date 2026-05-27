"""Curated read-only Postgres artifact queries for MCP tools."""
from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy import Select, String, cast, column, func, literal, or_, select, table
from sqlalchemy.ext.asyncio import async_sessionmaker

from api.application.artifact_contracts import (
    BodyArtifact,
    DNSRecordArtifact,
    EndpointArtifact,
    EndpointDetailArtifact,
    EventArtifact,
    FindingArtifact,
    HeaderArtifact,
    HostArtifact,
    IPArtifact,
    LeakArtifact,
    ParameterArtifact,
    ServiceArtifact,
)
from api.infrastructure.adapters.orm import (
    dns_records,
    endpoints,
    event_store,
    findings,
    headers,
    host_ips,
    hosts,
    input_parameters,
    ip_addresses,
    leaks,
    raw_body,
    services,
    vuln_types,
)

DEFAULT_LIMIT = 50
MAX_LIMIT = 100

LATEST_HTTP_OBSERVATIONS = table(
    "latest_http_observations",
    column("observation_id"),
    column("program_id"),
    column("endpoint_id"),
    column("service_id"),
    column("job_id"),
    column("run_id"),
    column("correlation_id"),
    column("raw_artifact_id"),
    column("method"),
    column("url"),
    column("status_code"),
    column("content_type"),
    column("title"),
    column("body_sha256"),
    column("body_size_bytes"),
    column("body_artifact_id"),
    column("body_preview"),
    column("source_tool"),
    column("observed_at"),
)

LATEST_HTTP_OBSERVATION_HEADERS = table(
    "latest_http_observation_headers",
    column("id"),
    column("endpoint_id"),
    column("observation_id"),
    column("name"),
    column("value"),
    column("ordinal"),
)


class ArtifactReaderError(ValueError):
    """Raised when an MCP artifact query violates the curated contract."""


class PostgresArtifactReader:
    """Read-only artifact reader built from fixed SQLAlchemy Core queries."""

    def __init__(self, session_factory: async_sessionmaker):
        self.session_factory = session_factory

    @staticmethod
    def clamp_limit(limit: int | None) -> int:
        if limit is None:
            return DEFAULT_LIMIT
        return max(1, min(int(limit), MAX_LIMIT))

    @staticmethod
    def clamp_offset(offset: int | None) -> int:
        if offset is None:
            return 0
        return max(0, int(offset))

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
        rows = await self._fetch_all(query.order_by(hosts.c.host), limit, offset)
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
        rows = await self._fetch_all(query.order_by(ip_addresses.c.address), limit, offset)
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
        rows = await self._fetch_all(query.order_by(ip_addresses.c.address, services.c.port), limit, offset)
        return [ServiceArtifact.model_validate(row) for row in rows]

    async def list_endpoints(
        self,
        program_id: uuid.UUID,
        host_id: uuid.UUID | None = None,
        method: str | None = None,
        status: int | None = None,
        q: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[EndpointArtifact]:
        query = self._endpoint_base_query().where(hosts.c.program_id == program_id)
        if host_id:
            query = query.where(endpoints.c.host_id == host_id)
        if method:
            query = query.where(endpoints.c.methods.op("@>")([method.upper()]))
        if status is not None:
            query = query.where(self._endpoint_status_code_expression() == status)
        if q:
            query = query.where(
                or_(
                    endpoints.c.path.ilike(f"%{q}%"),
                    endpoints.c.normalized_path.ilike(f"%{q}%"),
                    hosts.c.host.ilike(f"%{q}%"),
                )
            )
        rows = await self._fetch_all(query.order_by(hosts.c.host, endpoints.c.path), limit, offset)
        return [EndpointArtifact.model_validate(row) for row in rows]

    async def get_endpoint_detail(self, endpoint_id: uuid.UUID) -> EndpointDetailArtifact | None:
        async with self.session_factory() as session:
            result = await session.execute(
                self._endpoint_base_query().where(endpoints.c.id == endpoint_id)
            )
            row = result.mappings().first()
            if row is None:
                return None
            endpoint = EndpointDetailArtifact.model_validate(
                {
                    **dict(row),
                    "parameters": await self._endpoint_parameters(session, endpoint_id),
                    "headers": await self._endpoint_headers(session, endpoint_id),
                    "bodies": await self._endpoint_bodies(session, endpoint_id, include_content=False),
                }
            )
            return endpoint

    async def list_parameters(
        self,
        endpoint_id: uuid.UUID | None = None,
        program_id: uuid.UUID | None = None,
        location: str | None = None,
        name: str | None = None,
        reflected: bool | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[ParameterArtifact]:
        query = select(input_parameters)
        query = self._scope_endpoint_child_query(query, input_parameters, input_parameters.c.endpoint_id, endpoint_id, program_id)
        if location:
            query = query.where(input_parameters.c.location == location)
        if name:
            query = query.where(input_parameters.c.name.ilike(f"%{name}%"))
        if reflected is not None:
            query = query.where(input_parameters.c.reflected == reflected)
        rows = await self._fetch_all(query.order_by(input_parameters.c.location, input_parameters.c.name), limit, offset)
        return [ParameterArtifact.model_validate(row) for row in rows]

    async def list_headers(
        self,
        endpoint_id: uuid.UUID | None = None,
        program_id: uuid.UUID | None = None,
        name: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[HeaderArtifact]:
        query = select(
            LATEST_HTTP_OBSERVATION_HEADERS.c.id,
            LATEST_HTTP_OBSERVATION_HEADERS.c.endpoint_id,
            LATEST_HTTP_OBSERVATION_HEADERS.c.name,
            LATEST_HTTP_OBSERVATION_HEADERS.c.value,
        )
        query = self._scope_endpoint_child_query(
            query,
            LATEST_HTTP_OBSERVATION_HEADERS,
            LATEST_HTTP_OBSERVATION_HEADERS.c.endpoint_id,
            endpoint_id,
            program_id,
        )
        if name:
            query = query.where(LATEST_HTTP_OBSERVATION_HEADERS.c.name.ilike(f"%{name}%"))
        rows = await self._fetch_all(query.order_by(LATEST_HTTP_OBSERVATION_HEADERS.c.name), limit, offset)
        if rows:
            return [HeaderArtifact.model_validate(row) for row in rows]

        query = select(headers)
        query = self._scope_endpoint_child_query(query, headers, headers.c.endpoint_id, endpoint_id, program_id)
        if name:
            query = query.where(headers.c.name.ilike(f"%{name}%"))
        rows = await self._fetch_all(query.order_by(headers.c.name), limit, offset)
        return [HeaderArtifact.model_validate(row) for row in rows]

    async def list_bodies(
        self,
        endpoint_id: uuid.UUID | None = None,
        program_id: uuid.UUID | None = None,
        body_hash: str | None = None,
        include_content: bool = False,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[BodyArtifact]:
        query = self._latest_observation_body_query()
        query = self._scope_endpoint_child_query(
            query,
            LATEST_HTTP_OBSERVATIONS,
            LATEST_HTTP_OBSERVATIONS.c.endpoint_id,
            endpoint_id,
            program_id,
        )
        query = query.where(
            or_(
                LATEST_HTTP_OBSERVATIONS.c.body_sha256.is_not(None),
                LATEST_HTTP_OBSERVATIONS.c.body_artifact_id.is_not(None),
                LATEST_HTTP_OBSERVATIONS.c.body_preview.is_not(None),
            )
        )
        if body_hash:
            query = query.where(LATEST_HTTP_OBSERVATIONS.c.body_sha256 == body_hash)
        rows = await self._fetch_all(query.order_by(LATEST_HTTP_OBSERVATIONS.c.observed_at.desc()), limit, offset)
        if rows:
            return [BodyArtifact.model_validate(row) for row in rows]

        query = select(
            raw_body.c.id,
            raw_body.c.endpoint_id,
            raw_body.c.body_hash,
            cast(raw_body.c.id, String).label("body_ref"),
            func.length(raw_body.c.body_content).label("body_length"),
            func.substr(raw_body.c.body_content, 1, 500).label("body_preview"),
            literal(None).label("body_content"),
        )
        query = self._scope_endpoint_child_query(query, raw_body, raw_body.c.endpoint_id, endpoint_id, program_id)
        if body_hash:
            query = query.where(raw_body.c.body_hash == body_hash)
        rows = await self._fetch_all(query.order_by(raw_body.c.id), limit, offset)
        return [BodyArtifact.model_validate(row) for row in rows]

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
        rows = await self._fetch_all(query.order_by(hosts.c.host, dns_records.c.record_type), limit, offset)
        return [DNSRecordArtifact.model_validate(row) for row in rows]

    async def list_findings(
        self,
        program_id: uuid.UUID,
        severity: str | None = None,
        verified: bool | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[FindingArtifact]:
        query = (
            select(
                findings.c.id,
                findings.c.program_id,
                findings.c.vuln_type_id,
                vuln_types.c.code.label("vuln_code"),
                vuln_types.c.severity,
                findings.c.host_id,
                findings.c.endpoint_id,
                findings.c.parameter_id,
                findings.c.description,
                findings.c.evidence,
                findings.c.verified,
                findings.c.false_positive,
            )
            .select_from(findings.outerjoin(vuln_types, findings.c.vuln_type_id == vuln_types.c.id))
            .where(findings.c.program_id == program_id)
        )
        if severity:
            query = query.where(vuln_types.c.severity == severity)
        if verified is not None:
            query = query.where(findings.c.verified == verified)
        rows = await self._fetch_all(query.order_by(findings.c.id), limit, offset)
        return [FindingArtifact.model_validate(row) for row in rows]

    async def list_leaks(
        self,
        program_id: uuid.UUID,
        verified: bool | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[LeakArtifact]:
        query = select(leaks).where(leaks.c.program_id == program_id)
        if verified is not None:
            query = query.where(leaks.c.verified == verified)
        rows = await self._fetch_all(query.order_by(leaks.c.id), limit, offset)
        return [LeakArtifact.model_validate(row) for row in rows]

    async def list_events(
        self,
        program_id: uuid.UUID,
        event_type: str | None = None,
        profile: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[EventArtifact]:
        query = select(event_store).where(event_store.c.program_id == program_id)
        if event_type:
            query = query.where(event_store.c.event_type == event_type)
        if profile:
            query = query.where(event_store.c.profile == profile)
        rows = await self._fetch_all(query.order_by(event_store.c.created_at.desc()), limit, offset)
        return [EventArtifact.model_validate(row) for row in rows]

    @staticmethod
    def _endpoint_base_query() -> Select:
        return (
            select(
                endpoints.c.id,
                hosts.c.program_id,
                endpoints.c.host_id,
                hosts.c.host,
                endpoints.c.service_id,
                services.c.scheme,
                services.c.port,
                endpoints.c.path,
                endpoints.c.normalized_path,
                endpoints.c.methods,
                PostgresArtifactReader._endpoint_status_code_expression().label("status_code"),
            )
            .select_from(
                endpoints
                .join(hosts, endpoints.c.host_id == hosts.c.id)
                .join(services, endpoints.c.service_id == services.c.id)
                .outerjoin(
                    LATEST_HTTP_OBSERVATIONS,
                    LATEST_HTTP_OBSERVATIONS.c.endpoint_id == endpoints.c.id,
                )
            )
        )

    @staticmethod
    def _endpoint_status_code_expression():
        return func.coalesce(LATEST_HTTP_OBSERVATIONS.c.status_code, endpoints.c.status_code)

    @staticmethod
    def _latest_observation_body_query() -> Select:
        body_ref = func.coalesce(
            LATEST_HTTP_OBSERVATIONS.c.body_artifact_id,
            LATEST_HTTP_OBSERVATIONS.c.observation_id,
        )
        return select(
            body_ref.label("id"),
            LATEST_HTTP_OBSERVATIONS.c.endpoint_id,
            func.coalesce(
                LATEST_HTTP_OBSERVATIONS.c.body_sha256,
                cast(body_ref, String),
            ).label("body_hash"),
            cast(body_ref, String).label("body_ref"),
            func.coalesce(LATEST_HTTP_OBSERVATIONS.c.body_size_bytes, 0).label("body_length"),
            func.coalesce(LATEST_HTTP_OBSERVATIONS.c.body_preview, literal("")).label("body_preview"),
            literal(None).label("body_content"),
        )

    @staticmethod
    def _scope_endpoint_child_query(
        query: Select,
        child_table,
        child_endpoint_column,
        endpoint_id: uuid.UUID | None,
        program_id: uuid.UUID | None,
    ) -> Select:
        if endpoint_id is None and program_id is None:
            raise ArtifactReaderError("endpoint_id or program_id is required")
        if endpoint_id is not None:
            return query.where(child_endpoint_column == endpoint_id)
        return (
            query
            .select_from(
                child_table
                .join(endpoints, child_endpoint_column == endpoints.c.id)
                .join(hosts, endpoints.c.host_id == hosts.c.id)
            )
            .where(hosts.c.program_id == program_id)
        )

    async def _fetch_all(
        self,
        query: Select,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[Mapping[str, Any]]:
        query = query.limit(self.clamp_limit(limit)).offset(self.clamp_offset(offset))
        async with self.session_factory() as session:
            result = await session.execute(query)
            return list(result.mappings().all())

    @staticmethod
    async def _endpoint_parameters(session, endpoint_id: uuid.UUID) -> list[dict[str, Any]]:
        result = await session.execute(select(input_parameters).where(input_parameters.c.endpoint_id == endpoint_id))
        return [dict(row) for row in result.mappings().all()]

    @staticmethod
    async def _endpoint_headers(session, endpoint_id: uuid.UUID) -> list[dict[str, Any]]:
        result = await session.execute(
            select(
                LATEST_HTTP_OBSERVATION_HEADERS.c.id,
                LATEST_HTTP_OBSERVATION_HEADERS.c.endpoint_id,
                LATEST_HTTP_OBSERVATION_HEADERS.c.name,
                LATEST_HTTP_OBSERVATION_HEADERS.c.value,
            )
            .where(LATEST_HTTP_OBSERVATION_HEADERS.c.endpoint_id == endpoint_id)
            .order_by(LATEST_HTTP_OBSERVATION_HEADERS.c.ordinal, LATEST_HTTP_OBSERVATION_HEADERS.c.name)
        )
        rows = [dict(row) for row in result.mappings().all()]
        if rows:
            return rows

        result = await session.execute(select(headers).where(headers.c.endpoint_id == endpoint_id))
        return [dict(row) for row in result.mappings().all()]

    @staticmethod
    async def _endpoint_bodies(
        session,
        endpoint_id: uuid.UUID,
        include_content: bool,
    ) -> list[dict[str, Any]]:
        result = await session.execute(
            PostgresArtifactReader._latest_observation_body_query()
            .where(LATEST_HTTP_OBSERVATIONS.c.endpoint_id == endpoint_id)
            .where(
                or_(
                    LATEST_HTTP_OBSERVATIONS.c.body_sha256.is_not(None),
                    LATEST_HTTP_OBSERVATIONS.c.body_artifact_id.is_not(None),
                    LATEST_HTTP_OBSERVATIONS.c.body_preview.is_not(None),
                )
            )
            .order_by(LATEST_HTTP_OBSERVATIONS.c.observed_at.desc())
        )
        rows = [dict(row) for row in result.mappings().all()]
        if rows:
            return rows

        result = await session.execute(
            select(
                raw_body.c.id,
                raw_body.c.endpoint_id,
                raw_body.c.body_hash,
                cast(raw_body.c.id, String).label("body_ref"),
                func.length(raw_body.c.body_content).label("body_length"),
                func.substr(raw_body.c.body_content, 1, 500).label("body_preview"),
                literal(None).label("body_content"),
            ).where(raw_body.c.endpoint_id == endpoint_id)
        )
        return [dict(row) for row in result.mappings().all()]
