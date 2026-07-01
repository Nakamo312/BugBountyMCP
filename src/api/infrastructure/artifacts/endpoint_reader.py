"""Endpoint and endpoint-child artifact queries."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Select, or_, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from api.application.artifact_contracts import (
    EndpointArtifact,
    EndpointDetailArtifact,
    ParameterArtifact,
)
from api.infrastructure.adapters.orm import endpoints, hosts, input_parameters, services
from api.infrastructure.artifacts.common import (
    LATEST_HTTP_OBSERVATIONS,
    ArtifactQueryExecutor,
    endpoint_status_code_expression,
    scope_endpoint_child_query,
)
from api.infrastructure.artifacts.http_reader import HttpObservationArtifactReader


class EndpointArtifactReader:
    """Read endpoint summary/detail records and input parameters."""

    def __init__(
        self,
        executor: ArtifactQueryExecutor,
        session_factory: async_sessionmaker,
        http_reader: HttpObservationArtifactReader,
    ):
        self.executor = executor
        self.session_factory = session_factory
        self.http_reader = http_reader

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
        query = endpoint_base_query().where(hosts.c.program_id == program_id)
        if host_id:
            query = query.where(endpoints.c.host_id == host_id)
        if method:
            query = query.where(endpoints.c.methods.op("@>")([method.upper()]))
        if status is not None:
            query = query.where(endpoint_status_code_expression() == status)
        if q:
            query = query.where(
                or_(
                    endpoints.c.path.ilike(f"%{q}%"),
                    endpoints.c.normalized_path.ilike(f"%{q}%"),
                    hosts.c.host.ilike(f"%{q}%"),
                )
            )
        rows = await self.executor.fetch_all(
            query.order_by(hosts.c.host, endpoints.c.path),
            limit,
            offset,
        )
        return [EndpointArtifact.model_validate(row) for row in rows]

    async def get_endpoint_detail(self, endpoint_id: uuid.UUID) -> EndpointDetailArtifact | None:
        async with self.session_factory() as session:
            result = await session.execute(endpoint_base_query().where(endpoints.c.id == endpoint_id))
            row = result.mappings().first()
            if row is None:
                return None
            return EndpointDetailArtifact.model_validate(
                {
                    **dict(row),
                    "parameters": await endpoint_parameters(session, endpoint_id),
                    "headers": await self.http_reader.endpoint_headers(session, endpoint_id),
                    "bodies": await self.http_reader.endpoint_bodies(
                        session,
                        endpoint_id,
                        include_content=False,
                    ),
                }
            )

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
        query = scope_endpoint_child_query(
            query,
            input_parameters,
            input_parameters.c.endpoint_id,
            endpoint_id,
            program_id,
        )
        if location:
            query = query.where(input_parameters.c.location == location)
        if name:
            query = query.where(input_parameters.c.name.ilike(f"%{name}%"))
        if reflected is not None:
            query = query.where(input_parameters.c.reflected == reflected)
        rows = await self.executor.fetch_all(
            query.order_by(input_parameters.c.location, input_parameters.c.name),
            limit,
            offset,
        )
        return [ParameterArtifact.model_validate(row) for row in rows]


def endpoint_base_query() -> Select:
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
            endpoint_status_code_expression().label("status_code"),
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


async def endpoint_parameters(session, endpoint_id: uuid.UUID) -> list[dict[str, Any]]:
    result = await session.execute(select(input_parameters).where(input_parameters.c.endpoint_id == endpoint_id))
    return [dict(row) for row in result.mappings().all()]
