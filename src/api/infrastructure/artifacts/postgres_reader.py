"""Curated read-only Postgres artifact queries for MCP tools."""
from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

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
    RawArtifactPreview,
    ServiceArtifact,
)
from api.infrastructure.artifacts.asset_reader import AssetArtifactReader
from api.infrastructure.artifacts.common import (
    LATEST_HTTP_OBSERVATION_HEADERS,
    LATEST_HTTP_OBSERVATIONS,
    ArtifactQueryExecutor,
    ArtifactReaderError,
    clamp_limit,
    clamp_offset,
    endpoint_status_code_expression,
    latest_observation_body_query,
    sanitize_body_row,
    sanitize_header_row,
    sanitize_leak_row,
    scope_endpoint_child_query,
)
from api.infrastructure.artifacts.endpoint_reader import EndpointArtifactReader, endpoint_base_query, endpoint_parameters
from api.infrastructure.artifacts.http_reader import HttpObservationArtifactReader
from api.infrastructure.artifacts.security_reader import SecurityArtifactReader


class PostgresArtifactReader:
    """Compatibility façade over narrow artifact readers."""

    def __init__(self, session_factory: async_sessionmaker):
        self.session_factory = session_factory
        self.executor = ArtifactQueryExecutor(session_factory)
        self.assets = AssetArtifactReader(self.executor)
        self.http = HttpObservationArtifactReader(self.executor)
        self.endpoints = EndpointArtifactReader(
            self.executor,
            session_factory,
            self.http,
        )
        self.security = SecurityArtifactReader(self.executor)

    clamp_limit = staticmethod(clamp_limit)
    clamp_offset = staticmethod(clamp_offset)
    _sanitize_header_row = staticmethod(sanitize_header_row)
    _sanitize_body_row = staticmethod(sanitize_body_row)
    _sanitize_leak_row = staticmethod(sanitize_leak_row)
    _endpoint_base_query = staticmethod(endpoint_base_query)
    _endpoint_status_code_expression = staticmethod(endpoint_status_code_expression)
    _latest_observation_body_query = staticmethod(latest_observation_body_query)
    _scope_endpoint_child_query = staticmethod(scope_endpoint_child_query)
    _endpoint_parameters = staticmethod(endpoint_parameters)
    _endpoint_headers = staticmethod(HttpObservationArtifactReader.endpoint_headers)
    _endpoint_bodies = staticmethod(HttpObservationArtifactReader.endpoint_bodies)

    async def list_hosts(
        self,
        program_id: uuid.UUID,
        q: str | None = None,
        in_scope: bool | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[HostArtifact]:
        return await self.assets.list_hosts(program_id, q, in_scope, limit, offset)

    async def list_ips(
        self,
        program_id: uuid.UUID,
        q: str | None = None,
        in_scope: bool | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[IPArtifact]:
        return await self.assets.list_ips(program_id, q, in_scope, limit, offset)

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
        return await self.assets.list_services(
            program_id,
            host_id,
            port,
            scheme,
            tech,
            limit,
            offset,
        )

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
        return await self.endpoints.list_endpoints(
            program_id,
            host_id,
            method,
            status,
            q,
            limit,
            offset,
        )

    async def get_endpoint_detail(self, endpoint_id: uuid.UUID) -> EndpointDetailArtifact | None:
        return await self.endpoints.get_endpoint_detail(endpoint_id)

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
        return await self.endpoints.list_parameters(
            endpoint_id,
            program_id,
            location,
            name,
            reflected,
            limit,
            offset,
        )

    async def list_headers(
        self,
        endpoint_id: uuid.UUID | None = None,
        program_id: uuid.UUID | None = None,
        name: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[HeaderArtifact]:
        return await self.http.list_headers(endpoint_id, program_id, name, limit, offset)

    async def list_bodies(
        self,
        endpoint_id: uuid.UUID | None = None,
        program_id: uuid.UUID | None = None,
        body_hash: str | None = None,
        include_content: bool = False,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[BodyArtifact]:
        return await self.http.list_bodies(
            endpoint_id,
            program_id,
            body_hash,
            include_content,
            limit,
            offset,
        )

    async def list_artifact_previews(
        self,
        *,
        program_id: uuid.UUID,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[RawArtifactPreview]:
        return await self.security.list_artifact_previews(
            program_id=program_id,
            limit=limit,
            offset=offset,
        )

    async def list_dns_records(
        self,
        program_id: uuid.UUID,
        host_id: uuid.UUID | None = None,
        record_type: str | None = None,
        q: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[DNSRecordArtifact]:
        return await self.assets.list_dns_records(
            program_id,
            host_id,
            record_type,
            q,
            limit,
            offset,
        )

    async def list_findings(
        self,
        program_id: uuid.UUID,
        severity: str | None = None,
        verified: bool | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[FindingArtifact]:
        return await self.security.list_findings(program_id, severity, verified, limit, offset)

    async def list_leaks(
        self,
        program_id: uuid.UUID,
        verified: bool | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[LeakArtifact]:
        return await self.security.list_leaks(program_id, verified, limit, offset)

    async def list_events(
        self,
        program_id: uuid.UUID,
        event_type: str | None = None,
        profile: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[EventArtifact]:
        return await self.security.list_events(program_id, event_type, profile, limit, offset)

    async def _fetch_all(
        self,
        query,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[Mapping[str, Any]]:
        return await self.executor.fetch_all(query, limit, offset)


__all__ = [
    "ArtifactReaderError",
    "LATEST_HTTP_OBSERVATIONS",
    "LATEST_HTTP_OBSERVATION_HEADERS",
    "PostgresArtifactReader",
]
